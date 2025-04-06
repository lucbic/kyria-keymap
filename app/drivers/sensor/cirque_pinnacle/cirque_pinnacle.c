/*
 * Copyright (c) 2025 ZMK Contributors
 * SPDX-License-Identifier: MIT
 */

#define DT_DRV_COMPAT cirque_pinnacle

#include <zephyr/device.h>
#include <zephyr/drivers/i2c.h>
#include <zephyr/drivers/gpio.h>
#include <zephyr/input/input.h>
#include <zephyr/kernel.h>
#include <zephyr/sys/byteorder.h>
#include <zephyr/logging/log.h>

LOG_MODULE_REGISTER(cirque_pinnacle, CONFIG_SENSOR_LOG_LEVEL);

/* Pinnacle Register Addresses */
#define PINNACLE_REG_FIRMWARE_ID        0x00
#define PINNACLE_REG_FIRMWARE_VERSION   0x01
#define PINNACLE_REG_STATUS             0x02
#define PINNACLE_REG_SYSCONFIG1         0x03
#define PINNACLE_REG_FEEDCONFIG1        0x04
#define PINNACLE_REG_FEEDCONFIG2        0x05
#define PINNACLE_REG_FEEDCONFIG3        0x06
#define PINNACLE_REG_CALIBCONFIG1       0x07
#define PINNACLE_REG_PS2_AUX_CONTROL    0x08
#define PINNACLE_REG_SAMPLE_RATE        0x09
#define PINNACLE_REG_Z_IDLE             0x0A
#define PINNACLE_REG_Z_SCALER           0x0B
#define PINNACLE_REG_SLEEP_INTERVAL     0x0C
#define PINNACLE_REG_SLEEP_TIMER        0x0D
#define PINNACLE_REG_PACKET_BYTE_0      0x12
#define PINNACLE_REG_PACKET_BYTE_1      0x13
#define PINNACLE_REG_PACKET_BYTE_2      0x14
#define PINNACLE_REG_PACKET_BYTE_3      0x15
#define PINNACLE_REG_PACKET_BYTE_4      0x16
#define PINNACLE_REG_PACKET_BYTE_5      0x17

/* Register Access Protocol (RAP) */
#define PINNACLE_RAP_READ               0xA0
#define PINNACLE_RAP_WRITE              0x80

/* Feed Configuration 1 Register Bits */
#define PINNACLE_FEED_CONFIG1_DATA_MODE_ABSOLUTE  (1 << 1)
#define PINNACLE_FEED_CONFIG1_ENABLE_FEED         (1 << 0)

/* Status Register Bits */
#define PINNACLE_STATUS_SW_CC           (1 << 3)
#define PINNACLE_STATUS_SW_DR           (1 << 2)

/* Maximum values for absolute mode */
#define PINNACLE_ABS_X_MAX              2047
#define PINNACLE_ABS_Y_MAX              1535
#define PINNACLE_ABS_Z_MAX              63

/* Gesture detection thresholds */
#define GESTURE_THRESHOLD_DISTANCE      100
#define GESTURE_THRESHOLD_TIME_MS       300
#define GESTURE_THRESHOLD_VELOCITY      5

/* Gesture types */
enum cirque_gesture_type {
    GESTURE_NONE = 0,
    GESTURE_ZOOM_IN,
    GESTURE_ZOOM_OUT,
    GESTURE_ROTATE_CW,
    GESTURE_ROTATE_CCW,
    GESTURE_SCROLL_UP,
    GESTURE_SCROLL_DOWN,
    GESTURE_PAN_LEFT,
    GESTURE_PAN_RIGHT,
    GESTURE_FLICK_LEFT,
    GESTURE_FLICK_RIGHT,
    GESTURE_FLICK_UP,
    GESTURE_FLICK_DOWN
};

struct cirque_pinnacle_config {
    struct i2c_dt_spec i2c;
    struct gpio_dt_spec dr_gpio;
};

struct finger_data {
    uint16_t x;
    uint16_t y;
    uint8_t z;
    bool active;
    int64_t timestamp;
};

struct gesture_state {
    struct finger_data fingers[3];
    uint8_t finger_count;
    enum cirque_gesture_type current_gesture;
    int64_t gesture_start_time;
    bool gesture_active;
};

struct cirque_pinnacle_data {
    const struct device *dev;
    struct k_thread thread;
    struct k_sem sem;
    struct gesture_state gesture;
    
    K_KERNEL_STACK_MEMBER(thread_stack, CONFIG_CIRQUE_PINNACLE_THREAD_STACK_SIZE);
};

static int cirque_pinnacle_read_register(const struct device *dev, uint8_t reg, uint8_t *data)
{
    const struct cirque_pinnacle_config *config = dev->config;
    uint8_t cmd = PINNACLE_RAP_READ | (reg & 0x1F);
    
    return i2c_write_read_dt(&config->i2c, &cmd, 1, data, 1);
}

static int cirque_pinnacle_write_register(const struct device *dev, uint8_t reg, uint8_t data)
{
    const struct cirque_pinnacle_config *config = dev->config;
    uint8_t buf[2] = {PINNACLE_RAP_WRITE | (reg & 0x1F), data};
    
    return i2c_write_dt(&config->i2c, buf, sizeof(buf));
}

static int cirque_pinnacle_read_data(const struct device *dev)
{
    struct cirque_pinnacle_data *data = dev->data;
    const struct cirque_pinnacle_config *config = dev->config;
    uint8_t status;
    int ret;
    
    /* Check if data is ready */
    ret = cirque_pinnacle_read_register(dev, PINNACLE_REG_STATUS, &status);
    if (ret < 0) {
        return ret;
    }
    
    if (!(status & PINNACLE_STATUS_SW_DR)) {
        return 0; /* No data ready */
    }
    
    /* Read absolute data packet */
    uint8_t packet[6];
    uint8_t cmd = PINNACLE_RAP_READ | PINNACLE_REG_PACKET_BYTE_0;
    ret = i2c_write_read_dt(&config->i2c, &cmd, 1, packet, sizeof(packet));
    if (ret < 0) {
        return ret;
    }
    
    /* Clear data ready flag */
    ret = cirque_pinnacle_write_register(dev, PINNACLE_REG_STATUS, 0);
    if (ret < 0) {
        return ret;
    }
    
    /* Process the data packet */
    uint8_t button_status = packet[0];
    uint8_t x_low = packet[2];
    uint8_t y_low = packet[3];
    uint8_t xy_high = packet[4];
    uint8_t z = packet[5] & 0x3F;
    
    uint16_t x = x_low | ((xy_high & 0x0F) << 8);
    uint16_t y = y_low | ((xy_high & 0xF0) << 4);
    
    /* Update finger data */
    data->gesture.fingers[0].x = x;
    data->gesture.fingers[0].y = y;
    data->gesture.fingers[0].z = z;
    data->gesture.fingers[0].active = (z > 0);
    data->gesture.fingers[0].timestamp = k_uptime_get();
    
    /* Report basic touch data */
    if (z > 0) {
        input_report_abs(dev, INPUT_ABS_X, x, false, K_FOREVER);
        input_report_abs(dev, INPUT_ABS_Y, y, false, K_FOREVER);
        input_report_abs(dev, INPUT_ABS_Z, z, true, K_FOREVER);
    } else {
        input_report_abs(dev, INPUT_ABS_Z, 0, true, K_FOREVER);
    }
    
    return 0;
}

static void cirque_pinnacle_process_gestures(const struct device *dev)
{
    struct cirque_pinnacle_data *data = dev->data;
    struct gesture_state *gesture = &data->gesture;
    
    /* Basic gesture detection logic - this would be expanded in a full implementation */
    if (gesture->fingers[0].active) {
        /* Process single finger gestures */
        /* In a full implementation, we would track finger movements over time */
        /* and detect patterns for gestures like flicks, etc. */
    } else {
        /* Reset gesture state when no fingers are detected */
        gesture->current_gesture = GESTURE_NONE;
        gesture->gesture_active = false;
    }
}

static void cirque_pinnacle_thread(void *p1, void *p2, void *p3)
{
    const struct device *dev = p1;
    struct cirque_pinnacle_data *data = dev->data;
    
    while (1) {
        cirque_pinnacle_read_data(dev);
        
        if (IS_ENABLED(CONFIG_CIRQUE_PINNACLE_GESTURE_SUPPORT)) {
            cirque_pinnacle_process_gestures(dev);
        }
        
        k_msleep(CONFIG_CIRQUE_PINNACLE_POLL_INTERVAL_MS);
    }
}

static int cirque_pinnacle_init(const struct device *dev)
{
    struct cirque_pinnacle_data *data = dev->data;
    const struct cirque_pinnacle_config *config = dev->config;
    uint8_t fw_id, fw_ver;
    int ret;
    
    if (!i2c_is_ready_dt(&config->i2c)) {
        LOG_ERR("I2C bus not ready");
        return -ENODEV;
    }
    
    /* Initialize GPIO if data ready pin is provided */
    if (config->dr_gpio.port != NULL) {
        if (!gpio_is_ready_dt(&config->dr_gpio)) {
            LOG_ERR("Data ready GPIO not ready");
            return -ENODEV;
        }
        
        ret = gpio_pin_configure_dt(&config->dr_gpio, GPIO_INPUT);
        if (ret < 0) {
            LOG_ERR("Failed to configure data ready GPIO");
            return ret;
        }
    }
    
    /* Read firmware ID and version to verify communication */
    ret = cirque_pinnacle_read_register(dev, PINNACLE_REG_FIRMWARE_ID, &fw_id);
    if (ret < 0) {
        LOG_ERR("Failed to read firmware ID");
        return ret;
    }
    
    ret = cirque_pinnacle_read_register(dev, PINNACLE_REG_FIRMWARE_VERSION, &fw_ver);
    if (ret < 0) {
        LOG_ERR("Failed to read firmware version");
        return ret;
    }
    
    LOG_INF("Cirque Pinnacle touchpad found, FW ID: 0x%02x, FW Version: 0x%02x", fw_id, fw_ver);
    
    /* Configure the touchpad for absolute mode */
    ret = cirque_pinnacle_write_register(dev, PINNACLE_REG_FEEDCONFIG1, 
                                        PINNACLE_FEED_CONFIG1_DATA_MODE_ABSOLUTE | 
                                        PINNACLE_FEED_CONFIG1_ENABLE_FEED);
    if (ret < 0) {
        LOG_ERR("Failed to configure touchpad mode");
        return ret;
    }
    
    /* Initialize semaphore and thread */
    k_sem_init(&data->sem, 0, 1);
    data->dev = dev;
    
    k_thread_create(&data->thread, data->thread_stack,
                   CONFIG_CIRQUE_PINNACLE_THREAD_STACK_SIZE,
                   cirque_pinnacle_thread, (void *)dev, NULL, NULL,
                   CONFIG_CIRQUE_PINNACLE_THREAD_PRIORITY, 0, K_NO_WAIT);
    
    LOG_INF("Cirque Pinnacle touchpad initialized");
    return 0;
}

#define CIRQUE_PINNACLE_INIT(inst)                                                      \
    static const struct cirque_pinnacle_config cirque_pinnacle_config_##inst = {        \
        .i2c = I2C_DT_SPEC_INST_GET(inst),                                             \
        .dr_gpio = GPIO_DT_SPEC_INST_GET_OR(inst, dr_gpios, {0}),                      \
    };                                                                                  \
                                                                                        \
    static struct cirque_pinnacle_data cirque_pinnacle_data_##inst;                     \
                                                                                        \
    DEVICE_DT_INST_DEFINE(inst, cirque_pinnacle_init, NULL,                            \
                         &cirque_pinnacle_data_##inst, &cirque_pinnacle_config_##inst,  \
                         POST_KERNEL, CONFIG_CIRQUE_PINNACLE_INIT_PRIORITY,             \
                         NULL);

DT_INST_FOREACH_STATUS_OKAY(CIRQUE_PINNACLE_INIT)


#if defined(LV_LVGL_H_INCLUDE_SIMPLE)
#include "lvgl.h"
#elif defined(LV_LVGL_H_INCLUDE_SYSTEM)
#include <lvgl.h>
#elif defined(LV_BUILD_TEST)
#include "../lvgl.h"
#else
#include "lvgl/lvgl.h"
#endif

#ifndef LV_ATTRIBUTE_MEM_ALIGN
#define LV_ATTRIBUTE_MEM_ALIGN
#endif

#ifndef LV_ATTRIBUTE_UI_SYNA_SPEECH
#define LV_ATTRIBUTE_UI_SYNA_SPEECH
#endif

static const
LV_ATTRIBUTE_MEM_ALIGN LV_ATTRIBUTE_LARGE_CONST LV_ATTRIBUTE_UI_SYNA_SPEECH
uint8_t ui_syna_speech_map[] = {

    0x00,0x00,0x00,0xff,0xff,0xff,0xff,0xff,

    0xff,0xff,0xf0,
    0xe0,0x00,0x30,
    0xcf,0xff,0x90,
    0x9f,0xff,0xc0,
    0xbf,0xff,0xe0,
    0xbf,0xff,0xe0,
    0xbf,0xff,0xe0,
    0xbf,0xff,0xe0,
    0xbf,0xff,0xe0,
    0xbf,0xff,0xe0,
    0xbf,0xff,0xe0,
    0xbf,0xff,0xe0,
    0xbf,0xff,0xc0,
    0x9f,0xff,0xd0,
    0xcc,0x00,0x10,
    0xe9,0xff,0xf0,
    0xe3,0xff,0xf0,
    0xe7,0xff,0xf0,

};

const lv_image_dsc_t ui_syna_speech = {
  .header = {
    .magic = LV_IMAGE_HEADER_MAGIC,
    .cf = LV_COLOR_FORMAT_I1,
    .flags = 0,
    .w = 20,
    .h = 18,
    .stride = 3,
    .reserved_2 = 0,
  },
  .data_size = sizeof(ui_syna_speech_map),
  .data = ui_syna_speech_map,
  .reserved = NULL,
};


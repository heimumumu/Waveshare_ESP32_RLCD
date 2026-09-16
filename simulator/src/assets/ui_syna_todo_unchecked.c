
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

#ifndef LV_ATTRIBUTE_UI_SYNA_TODO_UNCHECKED
#define LV_ATTRIBUTE_UI_SYNA_TODO_UNCHECKED
#endif

static const
LV_ATTRIBUTE_MEM_ALIGN LV_ATTRIBUTE_LARGE_CONST LV_ATTRIBUTE_UI_SYNA_TODO_UNCHECKED
uint8_t ui_syna_todo_unchecked_map[] = {

    0x00,0x00,0x00,0xff,0xff,0xff,0xff,0xff,

    0xff,0xfe,
    0xc0,0x02,
    0xbf,0xfc,
    0xbf,0xfc,
    0xbf,0xfc,
    0xbf,0xfc,
    0xbf,0xfc,
    0xbf,0xfc,
    0xbf,0xfc,
    0xbf,0xfc,
    0xbf,0xfc,
    0xbf,0xfc,
    0xbf,0xfc,
    0xbf,0xfc,
    0xc0,0x02,

};

const lv_image_dsc_t ui_syna_todo_unchecked = {
  .header = {
    .magic = LV_IMAGE_HEADER_MAGIC,
    .cf = LV_COLOR_FORMAT_I1,
    .flags = 0,
    .w = 15,
    .h = 15,
    .stride = 2,
    .reserved_2 = 0,
  },
  .data_size = sizeof(ui_syna_todo_unchecked_map),
  .data = ui_syna_todo_unchecked_map,
  .reserved = NULL,
};


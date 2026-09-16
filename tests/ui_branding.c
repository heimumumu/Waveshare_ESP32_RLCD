// Copyright (c) 2026 黑沐. MIT License.
#include "lvgl.h"
#include "ui/ui.h"
#include <assert.h>
#include <stdio.h>
#include <string.h>
static unsigned char buffer[400*300*4];
static void flush(lv_display_t*d,const lv_area_t*a,uint8_t*p){(void)a;(void)p;lv_display_flush_ready(d);}
static void snapshot(lv_display_t*d,const char*base,const char*suffix){
 char path[4096];snprintf(path,sizeof(path),"%s.%s.ppm",base,suffix);lv_refr_now(d);
 FILE*f=fopen(path,"wb");assert(f);fprintf(f,"P6\n400 300\n255\n");
 for(int i=0;i<400*300;i++){fputc(buffer[i*4+2],f);fputc(buffer[i*4+1],f);fputc(buffer[i*4],f);}fclose(f);
}
int main(int argc, char **argv){
 assert(argc == 2);
 lv_init();lv_display_t*d=lv_display_create(400,300);
 lv_display_set_color_format(d,LV_COLOR_FORMAT_XRGB8888);
 lv_display_set_buffers(d,buffer,NULL,sizeof(buffer),LV_DISPLAY_RENDER_MODE_FULL);
 lv_display_set_flush_cb(d,flush);ui_init();
 assert(lv_obj_get_child_count(lv_layer_top())>0);
 lv_refr_now(d);
 char startup_path[4096];snprintf(startup_path,sizeof(startup_path),"%s.startup.ppm",argv[1]);
 FILE*startup=fopen(startup_path,"wb");assert(startup);
 fprintf(startup,"P6\n400 300\n255\n");
 for(int i=0;i<400*300;i++){fputc(buffer[i*4+2],startup);fputc(buffer[i*4+1],startup);fputc(buffer[i*4],startup);}fclose(startup);
 lv_tick_inc(2100);lv_timer_handler();
 assert(lv_obj_get_child_count(lv_layer_top())==0);
 ui_toggle_page();ui_toggle_page();ui_toggle_page();
 lv_obj_t*screen=lv_screen_active();int found=0;
 for(uint32_t i=0;i<lv_obj_get_child_count(screen);i++){
  lv_obj_t*c=lv_obj_get_child(screen,i);
  if(lv_obj_check_type(c,&lv_label_class)&&strstr(lv_label_get_text(c),"黑沐"))found=1;
 }
 assert(found);lv_refr_now(d);
 FILE*f=fopen(argv[1],"wb");fprintf(f,"P6\n400 300\n255\n");
 for(int i=0;i<400*300;i++){fputc(buffer[i*4+2],f);fputc(buffer[i*4+1],f);fputc(buffer[i*4],f);}fclose(f);
 ui_toggle_page();assert(lv_screen_active()!=screen);
 ui_update_environment(36,40,95,true,true);
 ui_update_codex_quota(75,88,true);
 ui_update_media(true,"paused","I Was King","ONE OK ROCK",47,239,"am I, when am I gonna start");
 ui_update_performance(5,62,8,true,21,41,true,41,true,7,0,0,true);
 snapshot(d,argv[1],"dashboard");
 ui_show_performance();snapshot(d,argv[1],"performance");
 puts("Splash dismissal and fourth-page navigation passed");return 0;
}

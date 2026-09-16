// Read-only AppleSMC temperature probe. ABI reference:
// https://github.com/metaspartan/mactop/blob/main/internal/app/smc.h
// Only READ_BYTES (5), READ_INDEX (8), READ_KEYINFO (9) are used.
#include <IOKit/IOKitLib.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include <math.h>

typedef struct { uint8_t major, minor, build, reserved; uint16_t release; } Version;
typedef struct { uint16_t version, length; uint32_t cpu, gpu, memory; } Limits;
typedef struct { uint32_t size, type; uint8_t attributes; } Info;
typedef struct {
    uint32_t key; Version version; Limits limits; Info info;
    uint8_t result, status, command; uint32_t index; uint8_t bytes[32];
} Packet;
_Static_assert(sizeof(Packet) == 80, "Unexpected SMC ABI");
static uint32_t fourcc(const char *s) {
    return (uint32_t)(uint8_t)s[0]<<24 | (uint32_t)(uint8_t)s[1]<<16 |
           (uint32_t)(uint8_t)s[2]<<8 | (uint8_t)s[3];
}
static int call(io_connect_t conn, Packet *in, Packet *out) {
    size_t size = sizeof(*out); memset(out, 0, size);
    return IOConnectCallStructMethod(conn, 2, in, sizeof(*in), out, &size) == KERN_SUCCESS
        && size == sizeof(*out) && out->result == 0;
}
static int read_key(io_connect_t conn, uint32_t key, Packet *value, Info *info) {
    Packet in = {0}, out;
    in.key = key; in.command = 9;
    if (!call(conn, &in, &out) || out.info.size > 32) return 0;
    *info = out.info; in.info.size = info->size; in.command = 5;
    return call(conn, &in, value);
}
static void emit(io_connect_t conn, const char *key, int *comma) {
    // A strict allowlist prevents accidentally querying unrelated SMC controls.
    if (strlen(key) != 4 || key[0] != 'T' || !strchr("peg", key[1])) return;
    for (int i=2;i<4;i++) if (!((key[i]>='0'&&key[i]<='9') ||
        (key[i]>='a'&&key[i]<='z') || (key[i]>='A'&&key[i]<='Z'))) return;
    Packet value; Info info;
    if (!read_key(conn, fourcc(key), &value, &info)) return;
    double temp;
    if (info.type == fourcc("flt ") && info.size == 4) {
        float v; memcpy(&v, value.bytes, 4); temp = v;
    } else if (info.type == fourcc("sp78") && info.size == 2) {
        temp = (int16_t)((uint16_t)value.bytes[0]<<8 | value.bytes[1]) / 256.0;
    } else return;
    if (!isfinite(temp) || temp <= 0 || temp >= 130) return;
    printf("%s\"%s\":%.3f", *comma ? "," : "", key, temp); *comma = 1;
}
int main(int argc, const char **argv) {
    io_service_t service = IOServiceGetMatchingService(0, IOServiceMatching("AppleSMC"));
    if (!service) { puts("{}"); return 0; }
    io_connect_t conn = 0;
    kern_return_t result = IOServiceOpen(service, mach_task_self(), 0, &conn);
    IOObjectRelease(service);
    if (result != KERN_SUCCESS) { puts("{}"); return 0; }
    int comma = 0; printf("{");
    if (argc > 1) {
        for (int i=1;i<argc;i++) emit(conn, argv[i], &comma);
    } else {
        Packet value; Info info;
        if (read_key(conn, fourcc("#KEY"), &value, &info) && info.size == 4) {
            uint32_t count = (uint32_t)value.bytes[0]<<24 | (uint32_t)value.bytes[1]<<16 |
                             (uint32_t)value.bytes[2]<<8 | value.bytes[3];
            if (count > 16384) count = 0;
            for (uint32_t i=0; i<count; i++) {
                Packet in = {0}, out; in.command = 8; in.index = i;
                if (!call(conn, &in, &out)) continue;
                char key[5] = {out.key>>24, out.key>>16, out.key>>8, out.key, 0};
                emit(conn, key, &comma);
            }
        }
    }
    puts("}"); IOServiceClose(conn); return 0;
}

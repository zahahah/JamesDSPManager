#define LOG_TAG "JDSPPinWrap"
#define ANDROID_LOG_INFO 4
#define ANDROID_LOG_ERROR 6
#define RTLD_LAZY 1
#define RTLD_NOW 2
#define RTLD_LOCAL 0
#define RTLD_NOLOAD 4
#define NULL ((void*)0)

#define JDSP_BINDER_EX_ILLEGAL_ARGUMENT (-3)

typedef signed int int32_t;
typedef struct {
    const char* dli_fname;
    void* dli_fbase;
    const char* dli_sname;
    void* dli_saddr;
} Dl_info;

extern int dladdr(const void* address, Dl_info* info);
extern void* dlopen(const char* filename, int flags);
extern void* dlsym(void* handle, const char* symbol);
extern const char* dlerror(void);
extern int __android_log_print(int priority, const char* tag, const char* format, ...);

typedef int32_t (*jdsp_query_effect_t)(const void* uuid, void* descriptor);
typedef int32_t (*jdsp_create_effect_t)(const void* uuid, void* effect);
typedef int32_t (*jdsp_destroy_effect_t)(const void* effect);

static void* g_self_pin;
static void* g_real_handle;
static jdsp_query_effect_t g_query_effect;
static jdsp_create_effect_t g_create_effect;
static jdsp_destroy_effect_t g_destroy_effect;

static void jdsp_log(int prio, const char* fmt, const char* value) {
    __android_log_print(prio, LOG_TAG, fmt, value ? value : "(null)");
}

static void pin_self_once(void) {
    if (g_self_pin != NULL) return;

    Dl_info info = {0};
    if (dladdr((void*)&pin_self_once, &info) == 0 || info.dli_fname == NULL) {
        jdsp_log(ANDROID_LOG_ERROR, "PinLibrary: dladdr failed", NULL);
        return;
    }

    /* Match ViPERFX_RE 2.1.1: retain one RTLD_NOLOAD reference to this DSO. */
    void* handle = dlopen(info.dli_fname, RTLD_LAZY | RTLD_NOLOAD);
    if (handle == NULL) {
        jdsp_log(ANDROID_LOG_ERROR, "PinLibrary: dlopen(RTLD_NOLOAD) failed: %s", dlerror());
        return;
    }
    g_self_pin = handle;
}

static void* open_real_library(void) {
    const char* candidates[] = {
        "/vendor/lib64/soundfx/libjamesdsp_real.so",
        "/odm/lib64/soundfx/libjamesdsp_real.so",
        "libjamesdsp_real.so",
        0,
    };

    for (int i = 0; candidates[i] != NULL; ++i) {
        void* handle = dlopen(candidates[i], RTLD_NOW | RTLD_LOCAL);
        if (handle != NULL) {
            jdsp_log(ANDROID_LOG_INFO, "Loaded real JamesDSP AIDL library: %s", candidates[i]);
            return handle;
        }
    }
    jdsp_log(ANDROID_LOG_ERROR, "Failed to load real JamesDSP AIDL library: %s", dlerror());
    return NULL;
}

static int ensure_real_symbols(void) {
    pin_self_once();
    if (g_real_handle != NULL && g_query_effect != NULL &&
        g_create_effect != NULL && g_destroy_effect != NULL) {
        return 1;
    }

    if (g_real_handle == NULL) {
        g_real_handle = open_real_library();
        if (g_real_handle == NULL) return 0;
    }

    g_query_effect = (jdsp_query_effect_t)dlsym(g_real_handle, "queryEffect");
    g_create_effect = (jdsp_create_effect_t)dlsym(g_real_handle, "createEffect");
    g_destroy_effect = (jdsp_destroy_effect_t)dlsym(g_real_handle, "destroyEffect");
    if (g_query_effect == NULL || g_create_effect == NULL || g_destroy_effect == NULL) {
        jdsp_log(ANDROID_LOG_ERROR, "Missing real JamesDSP AIDL symbol: %s", dlerror());
        return 0;
    }
    return 1;
}

__attribute__((visibility("default"))) int32_t queryEffect(const void* uuid, void* descriptor) {
    if (!ensure_real_symbols()) return JDSP_BINDER_EX_ILLEGAL_ARGUMENT;
    return g_query_effect(uuid, descriptor);
}

__attribute__((visibility("default"))) int32_t createEffect(const void* uuid, void* effect) {
    if (!ensure_real_symbols()) return JDSP_BINDER_EX_ILLEGAL_ARGUMENT;
    return g_create_effect(uuid, effect);
}

__attribute__((visibility("default"))) int32_t destroyEffect(const void* effect) {
    if (!ensure_real_symbols()) return JDSP_BINDER_EX_ILLEGAL_ARGUMENT;
    return g_destroy_effect(effect);
}

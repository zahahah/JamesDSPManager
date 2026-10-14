#ifndef BUILD_LIBLOG
void* dlopen(const char* filename, int flags) {
    (void)filename;
    (void)flags;
    return 0;
}

void* dlsym(void* handle, const char* symbol) {
    (void)handle;
    (void)symbol;
    return 0;
}

int dladdr(const void* address, void* info) {
    (void)address;
    (void)info;
    return 0;
}

const char* dlerror(void) {
    return 0;
}
#else
int __android_log_print(int priority, const char* tag, const char* format, ...) {
    (void)priority;
    (void)tag;
    (void)format;
    return 0;
}
#endif

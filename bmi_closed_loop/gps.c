#include <stdio.h>
#include <stdlib.h>
#include <fcntl.h>
#include <unistd.h>
#include <time.h>
#include <errno.h>
#include <string.h>
#include <timepps.h>

int main(void)
{
    int fd = open("/dev/pps0", O_RDWR);
    if (fd < 0) { perror("open /dev/pps0"); return 1; }

    pps_handle_t handle;
    if (time_pps_create(fd, &handle) < 0) {
        perror("time_pps_create"); return 1;
    }

    /* Check the device can capture the assert (rising) edge */
    int cap = 0;
    time_pps_getcap(handle, &cap);
    if (!(cap & PPS_CAPTUREASSERT)) {
        fprintf(stderr, "Device cannot capture assert edge\n"); return 1;
    }

    /* Enable assert capture */
    pps_params_t params;
    time_pps_getparams(handle, &params);
    params.mode |= PPS_CAPTUREASSERT | PPS_TSFMT_TSPEC;
    time_pps_setparams(handle, &params);

    printf("%-20s  %-20s  %s\n",
           "pps_realtime_ns", "monotonic_ns", "seq");

    struct timespec timeout = { .tv_sec = 3, .tv_nsec = 0 };
    pps_info_t info;
    unsigned int last_seq = 0;

    while (1) {
        int ret = time_pps_fetch(handle, PPS_TSFMT_TSPEC, &info, &timeout);
        if (ret < 0) { perror("pps_fetch"); continue; }

        /* Skip if no new pulse arrived */
        if (info.assert_sequence == last_seq) continue;
        last_seq = info.assert_sequence;

        /* Read CLOCK_MONOTONIC as close as possible after the pulse */
        struct timespec mono;
        clock_gettime(CLOCK_MONOTONIC, &mono);

        long long pps_ns  = (long long)info.assert_timestamp.tv_sec * 1000000000LL
                          + info.assert_timestamp.tv_nsec;
        long long mono_ns = (long long)mono.tv_sec * 1000000000LL
                          + mono.tv_nsec;

        printf("%-20lld  %-20lld  %u\n", pps_ns, mono_ns, last_seq);
        fflush(stdout);
    }

    time_pps_destroy(handle);
    close(fd);
    return 0;
}
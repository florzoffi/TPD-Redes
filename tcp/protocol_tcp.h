#ifndef PROTOCOL_TCP_H
#define PROTOCOL_TCP_H

#include <stdint.h>
#include <sys/time.h>

#define SERVER_PORT 20252
#define MIN_PAYLOAD 500
#define MAX_PAYLOAD 1000
#define DELIMITER   '|'

// timestamp en microsegundos desde epoch
static inline uint64_t now_us(void) {
    struct timeval tv;
    gettimeofday(&tv, NULL);
    return (uint64_t)tv.tv_sec * 1000000ULL + (uint64_t)tv.tv_usec;
}

#endif

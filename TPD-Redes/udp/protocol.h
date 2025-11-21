#ifndef PROTOCOL_H
#define PROTOCOL_H

#define TYPE_HELLO 1
#define TYPE_WRQ   2
#define TYPE_DATA  3
#define TYPE_ACK   4
#define TYPE_FIN   5

#define SERVER_PORT 20252
#define MAX_DATA_SIZE 1478
#define FILENAME_MIN_LEN 4
#define FILENAME_MAX_LEN 10

#define MAX_RETRIES 15
#define TIMEOUT_MS 3000

typedef struct {
    uint8_t type;
    uint8_t seq;
    uint8_t data[MAX_DATA_SIZE];
    size_t data_len;
} pdu_t;

#endif
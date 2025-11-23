#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
#include <arpa/inet.h>

#include "protocol_tcp.h"

#include <time.h> 

int main(int argc, char *argv[]) {

    if (argc != 5) {
        fprintf(stderr, "Uso: %s -d <ms_entre_envios> -N <segundos_total>\n", argv[0]);
        return EXIT_FAILURE;
    }

    int d_ms = 0;   
    int N_sec = 0;  

    if (strcmp(argv[1], "-d") == 0) {
        d_ms = atoi(argv[2]);
    } else {
        fprintf(stderr, "Se esperaba -d\n");
        return EXIT_FAILURE;
    }

    if (strcmp(argv[3], "-N") == 0) {
        N_sec = atoi(argv[4]);
    } else {
        fprintf(stderr, "Se esperaba -N\n");
        return EXIT_FAILURE;
    }

    if (d_ms <= 0 || N_sec <= 0) {
        fprintf(stderr, "Valores de d y N deben ser > 0\n");
        return EXIT_FAILURE;
    }

    srand(time(NULL)); 

    int sock;
    struct sockaddr_in server_addr;

    sock = socket(AF_INET, SOCK_STREAM, 0);
    if (sock < 0) {
        perror("socket");
        exit(EXIT_FAILURE);
    }

    memset(&server_addr, 0, sizeof(server_addr));
    server_addr.sin_family = AF_INET;
    server_addr.sin_port   = htons(SERVER_PORT);
    server_addr.sin_addr.s_addr = htonl(INADDR_LOOPBACK);

    if (connect(sock, (struct sockaddr *)&server_addr, sizeof(server_addr)) < 0) {
        perror("connect");
        close(sock);
        exit(EXIT_FAILURE);
    }

    printf("Conectado al servidor.\n");

    uint64_t start_us = now_us();
    uint64_t end_us   = start_us + (uint64_t)N_sec * 1000000ULL;
    int envio = 0;

    while (now_us() < end_us) {

        uint64_t ts = now_us();

        int payload_size = MIN_PAYLOAD + rand() % (MAX_PAYLOAD - MIN_PAYLOAD + 1);
        int total_size   = 8 + payload_size + 1;

        uint8_t *buffer = malloc(total_size);
        if (!buffer) {
            perror("malloc");
            break;
        }

        memcpy(buffer, &ts, 8);
        memset(buffer + 8, 0x20, payload_size);
        buffer[8 + payload_size] = DELIMITER;

        ssize_t n = write(sock, buffer, total_size);
        if (n < 0) {
            perror("write");
            free(buffer);
            break;
        }

        envio++;
        printf("Envio %d: mande %zd bytes\n", envio, n);

        free(buffer);

        usleep(d_ms * 1000); 
    }

    close(sock);
    return 0;
}

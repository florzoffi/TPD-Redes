#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
#include <arpa/inet.h>

#include "protocol_tcp.h"

int main(void) {
    int listen_fd, client_fd;
    struct sockaddr_in addr, cliaddr;
    socklen_t cli_len = sizeof(cliaddr);

    listen_fd = socket(AF_INET, SOCK_STREAM, 0);
    if (listen_fd < 0) {
        perror("socket");
        exit(EXIT_FAILURE);
    }

    int opt = 1;
    setsockopt(listen_fd, SOL_SOCKET, SO_REUSEADDR, &opt, sizeof(opt));

    memset(&addr, 0, sizeof(addr));
    addr.sin_family      = AF_INET;
    addr.sin_addr.s_addr = htonl(INADDR_ANY);
    addr.sin_port        = htons(SERVER_PORT);

    if (bind(listen_fd, (struct sockaddr *)&addr, sizeof(addr)) < 0) {
        perror("bind");
        close(listen_fd);
        exit(EXIT_FAILURE);
    }

    if (listen(listen_fd, 1) < 0) {
        perror("listen");
        close(listen_fd);
        exit(EXIT_FAILURE);
    }

    printf("TCP server escuchando en puerto %d...\n", SERVER_PORT);

    client_fd = accept(listen_fd, (struct sockaddr *)&cliaddr, &cli_len);
    if (client_fd < 0) {
        perror("accept");
        close(listen_fd);
        exit(EXIT_FAILURE);
    }

    printf("Cliente conectado.\n");

    unsigned char buf[2048];
    ssize_t n;

    unsigned char recvbuf[2048];
    unsigned char framebuf[12000];
    int frame_len = 0;

    int measurement_id = 1;
    FILE *f = fopen("delay.csv", "w");
    if (!f) {
        perror("fopen delay.csv");
        close(client_fd);
        close(listen_fd);
        exit(EXIT_FAILURE);
    }


    while ((n = read(client_fd, recvbuf, sizeof(recvbuf))) > 0) {
        for (int i = 0; i < n; i++) {
            framebuf[frame_len++] = recvbuf[i];

            if (recvbuf[i] == DELIMITER) {
                // Solo procesamos si hay al menos 8 bytes (el timestamp)
                if (frame_len > 8) {

                    uint64_t ts_origin;
                    memcpy(&ts_origin, framebuf, 8);

                    uint64_t ts_dest = now_us();
                    double delay_s = (ts_dest - ts_origin) / 1e6;

                    // Guardar en CSV: numero de medición, delay
                    fprintf(f, "%d,%.6f\n", measurement_id, delay_s);
                    fflush(f);

                    printf("Delay %d: %.6f segundos\n", measurement_id, delay_s);

                    measurement_id++;
                }

                // Reset del acumulador para la próxima PDU
                frame_len = 0;
            }

        }
    }

    fclose(f);

    if (n < 0) {
        perror("read");
    }

    close(client_fd);
    close(listen_fd);
    return 0;
}

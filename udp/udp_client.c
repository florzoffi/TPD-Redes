// udp_client.c
#define _POSIX_C_SOURCE 200112L

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <stdint.h>
#include <errno.h>
#include <unistd.h>
#include <arpa/inet.h>
#include <sys/socket.h>
#include <sys/time.h>

#include "protocol.h"

// ---------- helpers de PDU (serializar / deserializar) ----------

static int send_pdu(int sock,
                    const struct sockaddr_in *addr,
                    const pdu_t *pdu) {
    uint8_t buffer[2 + MAX_DATA_SIZE];
    size_t len = 2 + pdu->data_len;

    buffer[0] = pdu->type;
    buffer[1] = pdu->seq;
    if (pdu->data_len > 0) {
        memcpy(&buffer[2], pdu->data, pdu->data_len);
    }

    ssize_t sent = sendto(sock, buffer, len, 0,
                          (const struct sockaddr *)addr,
                          sizeof(*addr));
    if (sent < 0) {
        perror("sendto");
        return -1;
    }
    return 0;
}

static int recv_pdu(int sock,
                    struct sockaddr_in *addr,
                    pdu_t *pdu) {
    uint8_t buffer[2 + MAX_DATA_SIZE];
    socklen_t addrlen = sizeof(*addr);

    ssize_t n = recvfrom(sock, buffer, sizeof(buffer), 0,
                         (struct sockaddr *)addr, &addrlen);
    if (n < 0) {
        // timeout u otro error
        return -1;
    }
    if (n < 2) {
        // paquete inválido
        return -1;
    }

    pdu->type = buffer[0];
    pdu->seq  = buffer[1];
    pdu->data_len = (size_t)(n - 2);
    if (pdu->data_len > 0) {
        memcpy(pdu->data, &buffer[2], pdu->data_len);
    }
    return 0;
}

static void set_socket_timeout(int sock, int timeout_ms) {
    struct timeval tv;
    tv.tv_sec = timeout_ms / 1000;
    tv.tv_usec = (timeout_ms % 1000) * 1000;
    if (setsockopt(sock, SOL_SOCKET, SO_RCVTIMEO,
                   &tv, sizeof(tv)) < 0) {
        perror("setsockopt(SO_RCVTIMEO)");
        exit(EXIT_FAILURE);
    }
}

// Envía una PDU y espera un ACK con type=TYPE_ACK y seq esperado
// con reintentos y timeout
static int send_and_wait_ack(int sock,
                             struct sockaddr_in *server_addr,
                             const pdu_t *to_send,
                             uint8_t expected_ack_seq,
                             pdu_t *ack_out) {
    for (int attempt = 0; attempt < MAX_RETRIES; ++attempt) {
        if (send_pdu(sock, server_addr, to_send) < 0) {
            return -1;
        }

        // Esperar ACK
        pdu_t recv_p;
        struct sockaddr_in from;
        int r = recv_pdu(sock, &from, &recv_p);
        if (r < 0) {
            // timeout u otro error → reintentar
            fprintf(stderr, "[CLIENT] Timeout o error esperando ACK (intento %d)\n", attempt + 1);
            continue;
        }

        // Filtrar: que venga del mismo server (dirección + puerto)
        if (from.sin_addr.s_addr != server_addr->sin_addr.s_addr ||
            from.sin_port        != server_addr->sin_port) {
            fprintf(stderr, "[CLIENT] Paquete de origen desconocido, ignorado\n");
            continue;
        }

        if (recv_p.type != TYPE_ACK) {
            fprintf(stderr, "[CLIENT] Recibí PDU no-ACK, ignorando\n");
            continue;
        }

        if (recv_p.seq != expected_ack_seq) {
            fprintf(stderr, "[CLIENT] ACK con seq incorrecto (recibí %u, esperaba %u)\n",
                    recv_p.seq, expected_ack_seq);
            // ignorar y reintentar
            continue;
        }

        // ACK correcto 👍
        if (ack_out) {
            *ack_out = recv_p;
        }
        return 0;
    }

    fprintf(stderr, "[CLIENT] No se recibió ACK válido después de %d intentos\n", MAX_RETRIES);
    return -1;
}

// ---------- Fases del protocolo ----------

static int fase_hello(int sock,
                      struct sockaddr_in *server_addr,
                      const char *credential,
                      uint8_t *seq) {
    pdu_t pdu = {0};
    pdu.type = TYPE_HELLO;
    pdu.seq  = *seq; // debería ser 0

    size_t cred_len = strlen(credential) + 1; // mando con '\0'
    if (cred_len > MAX_DATA_SIZE) {
        fprintf(stderr, "Credencial demasiado larga\n");
        return -1;
    }
    memcpy(pdu.data, credential, cred_len);
    pdu.data_len = cred_len;

    pdu_t ack;
    if (send_and_wait_ack(sock, server_addr, &pdu, *seq, &ack) < 0) {
        return -1;
    }

    if (ack.data_len > 0) {
        // Server mandó mensaje de error
        fprintf(stderr, "[CLIENT] Error en HELLO: %.*s\n",
                (int)ack.data_len, ack.data);
        return -1;
    }

    printf("[CLIENT] HELLO ok\n");
    // Stop & wait: solo incremento (toggle) si no hubo retransmisión final
    *seq ^= 1;
    return 0;
}

static int fase_wrq(int sock,
                    struct sockaddr_in *server_addr,
                    const char *remote_filename,
                    uint8_t *seq) {
    size_t len = strlen(remote_filename);
    if (len < FILENAME_MIN_LEN || len > FILENAME_MAX_LEN) {
        fprintf(stderr, "Filename inválido (debe tener entre %d y %d chars)\n",
                FILENAME_MIN_LEN, FILENAME_MAX_LEN);
        return -1;
    }

    pdu_t pdu = {0};
    pdu.type = TYPE_WRQ;
    pdu.seq  = *seq; // debería ser 1

    size_t fn_len = len + 1; // mando con '\0'
    memcpy(pdu.data, remote_filename, fn_len);
    pdu.data_len = fn_len;

    pdu_t ack;
    if (send_and_wait_ack(sock, server_addr, &pdu, *seq, &ack) < 0) {
        return -1;
    }

    if (ack.data_len > 0) {
        fprintf(stderr, "[CLIENT] Error en WRQ: %.*s\n",
                (int)ack.data_len, ack.data);
        return -1;
    }

    printf("[CLIENT] WRQ ok\n");
    *seq ^= 1; // ahora el próximo DATA arranca en 0
    return 0;
}

static int fase_data(int sock,
                     struct sockaddr_in *server_addr,
                     FILE *fp,
                     uint8_t *seq) {
    pdu_t pdu;
    pdu_t ack;
    size_t n;

    while ((n = fread(pdu.data, 1, MAX_DATA_SIZE, fp)) > 0) {
        pdu.type = TYPE_DATA;
        pdu.seq  = *seq;
        pdu.data_len = n;

        printf("[CLIENT] Enviando DATA seq=%u, bytes=%zu\n", pdu.seq, n);

        if (send_and_wait_ack(sock, server_addr, &pdu, *seq, &ack) < 0) {
            return -1;
        }

        printf("[CLIENT] ACK OK para seq=%u\n", *seq);
        *seq ^= 1; // alterno 0/1 solo si ACK fue correcto
    }

    if (ferror(fp)) {
        perror("fread");
        return -1;
    }

    printf("[CLIENT] Fase DATA completada\n");
    return 0;
}

static int fase_fin(int sock,
                    struct sockaddr_in *server_addr,
                    const char *remote_filename,
                    uint8_t *seq) {
    pdu_t pdu = {0};
    pdu.type = TYPE_FIN;
    pdu.seq  = *seq;

    size_t fn_len = strlen(remote_filename) + 1;
    if (fn_len > MAX_DATA_SIZE) {
        fprintf(stderr, "Filename demasiado largo para FIN\n");
        return -1;
    }
    memcpy(pdu.data, remote_filename, fn_len);
    pdu.data_len = fn_len;

    pdu_t ack;
    if (send_and_wait_ack(sock, server_addr, &pdu, *seq, &ack) < 0) {
        return -1;
    }

    if (ack.data_len > 0) {
        fprintf(stderr, "[CLIENT] Error en FIN: %.*s\n",
                (int)ack.data_len, ack.data);
        return -1;
    }

    printf("[CLIENT] FIN ok\n");
    *seq ^= 1;
    return 0;
}

// ---------- main ----------

int main(int argc, char *argv[]) {
    if (argc != 5) {
        fprintf(stderr, "Uso: %s <server_ip> <credential> <local_file> <remote_filename>\n",
                argv[0]);
        return EXIT_FAILURE;
    }

    const char *server_ip      = argv[1];
    const char *credential     = argv[2];
    const char *local_filename = argv[3];
    const char *remote_filename= argv[4];

    int sock = socket(AF_INET, SOCK_DGRAM, 0);
    if (sock < 0) {
        perror("socket");
        return EXIT_FAILURE;
    }

    set_socket_timeout(sock, TIMEOUT_MS);

    struct sockaddr_in server_addr;
    memset(&server_addr, 0, sizeof(server_addr));
    server_addr.sin_family = AF_INET;
    server_addr.sin_port   = htons(SERVER_PORT);

    if (inet_pton(AF_INET, server_ip, &server_addr.sin_addr) <= 0) {
        perror("inet_pton");
        close(sock);
        return EXIT_FAILURE;
    }

    FILE *fp = fopen(local_filename, "rb");
    if (!fp) {
        perror("fopen local file");
        close(sock);
        return EXIT_FAILURE;
    }

    uint8_t seq = 0;

    if (fase_hello(sock, &server_addr, credential, &seq) < 0) goto error;
    if (fase_wrq(sock, &server_addr, remote_filename, &seq) < 0) goto error;
    if (fase_data(sock, &server_addr, fp, &seq) < 0) goto error;
    if (fase_fin(sock, &server_addr, remote_filename, &seq) < 0) goto error;

    printf("[CLIENT] Transferencia completa.\n");
    fclose(fp);
    close(sock);
    return EXIT_SUCCESS;

error:
    fprintf(stderr, "[CLIENT] Error en la transferencia.\n");
    fclose(fp);
    close(sock);
    return EXIT_FAILURE;
}

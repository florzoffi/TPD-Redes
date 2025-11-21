// udp_server.c
#define _POSIX_C_SOURCE 200112L

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <stdint.h>
#include <errno.h>
#include <unistd.h>
#include <arpa/inet.h>
#include <sys/socket.h>

#include "protocol.h"

#define MAX_CLIENTS 32

typedef enum {
    STATE_WAIT_HELLO = 0,
    STATE_WAIT_WRQ,
    STATE_TRANSFER,
    STATE_FINISHED
} client_state_e;

typedef struct {
    int used;
    struct sockaddr_in addr;
    client_state_e state;
    uint8_t expected_seq;                   // para DATA
    FILE *fp;
    char filename[FILENAME_MAX_LEN + 1];
} client_t;

static client_t clients[MAX_CLIENTS];

// Prototipos de handlers
static void handle_hello(int sock, int idx, const pdu_t *pdu);
static void handle_wrq  (int sock, int idx, const pdu_t *pdu);
static void handle_data (int sock, int idx, const pdu_t *pdu);
static void handle_fin  (int sock, int idx, const pdu_t *pdu);

static const char *VALID_CREDENTIAL = "g17-d111";


// ---------- helpers ----------

static int addr_equals(const struct sockaddr_in *a,
                       const struct sockaddr_in *b) {
    return (a->sin_addr.s_addr == b->sin_addr.s_addr) &&
           (a->sin_port        == b->sin_port);
}

static int find_or_create_client(const struct sockaddr_in *addr) {
    int free_idx = -1;

    for (int i = 0; i < MAX_CLIENTS; ++i) {
        if (clients[i].used) {
            if (addr_equals(&clients[i].addr, addr)) {
                return i;
            }
        } else if (free_idx == -1) {
            free_idx = i;
        }
    }

    if (free_idx == -1) {
        return -1; // no hay lugar
    }

    clients[free_idx].used = 1;
    clients[free_idx].addr = *addr;
    clients[free_idx].state = STATE_WAIT_HELLO;
    clients[free_idx].expected_seq = 0;
    clients[free_idx].fp = NULL;
    clients[free_idx].filename[0] = '\0';

    printf("[SERVER] Nuevo cliente en slot %d\n", free_idx);
    return free_idx;
}

static void reset_client(int idx) {
    if (clients[idx].fp) {
        fclose(clients[idx].fp);
        clients[idx].fp = NULL;
    }
    clients[idx].used = 0;
    clients[idx].state = STATE_FINISHED;
    clients[idx].filename[0] = '\0';
    printf("[SERVER] Liberando cliente slot %d\n", idx);
}

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
        perror("recvfrom");
        return -1;
    }
    if (n < 2) {
        fprintf(stderr, "[SERVER] PDU demasiado chica\n");
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

// ---------- handlers de fases ----------

static void handle_hello(int sock, int idx, const pdu_t *pdu) {
    pdu_t resp = {0};
    resp.type = TYPE_ACK;
    resp.seq  = pdu->seq;

    const char *error_msg = NULL;

    // La credencial esperada es "TEST"
    size_t expected_len = strlen(VALID_CREDENTIAL);

    // Debe tener exactamente ese largo y coincidir byte a byte
    if (pdu->data_len != expected_len ||
        memcmp(pdu->data, VALID_CREDENTIAL, expected_len) != 0) {
        error_msg = "Credencial invalida";
    }

    if (error_msg != NULL) {
        size_t msg_len = strlen(error_msg);
        memcpy(resp.data, error_msg, msg_len);
        resp.data_len = msg_len;
        printf("[SERVER] HELLO inválido de cliente %d\n", idx);
    } else {
        // credencial OK → pasar a WAIT_WRQ
        clients[idx].state = STATE_WAIT_WRQ;
        resp.data_len = 0;
        printf("[SERVER] HELLO OK de cliente %d\n", idx);
    }

    (void)send_pdu(sock, &clients[idx].addr, &resp);
}


static void handle_wrq(int sock, int idx, const pdu_t *pdu) {
    pdu_t resp = {0};
    resp.type = TYPE_ACK;
    resp.seq  = pdu->seq;

    // Validar que esté en el estado correcto
    if (clients[idx].state != STATE_WAIT_WRQ) {
        const char *msg = "WRQ fuera de fase";
        memcpy(resp.data, msg, strlen(msg));
        resp.data_len = strlen(msg);
        (void)send_pdu(sock, &clients[idx].addr, &resp);
        return;
    }

    const char *filename = (const char *)pdu->data;

    // 🔧 Reemplazo de strnlen: calculo largo a mano, pero máximo FILENAME_MAX_LEN+2
    size_t len = 0;
    while (len < FILENAME_MAX_LEN + 2 && filename[len] != '\0') {
        len++;
    }

    if (len < FILENAME_MIN_LEN || len > FILENAME_MAX_LEN) {
        const char *msg = "Filename invalido";
        memcpy(resp.data, msg, strlen(msg));
        resp.data_len = strlen(msg);
        (void)send_pdu(sock, &clients[idx].addr, &resp);
        return;
    }

    strncpy(clients[idx].filename, filename, FILENAME_MAX_LEN);
    clients[idx].filename[FILENAME_MAX_LEN] = '\0';

    // Abrimos archivo para escritura (modo binario)
    if (clients[idx].fp) {
        fclose(clients[idx].fp);
    }

    clients[idx].fp = fopen(clients[idx].filename, "wb");
    if (!clients[idx].fp) {
        perror("fopen");
        const char *msg = "No se pudo abrir archivo";
        memcpy(resp.data, msg, strlen(msg));
        resp.data_len = strlen(msg);
        (void)send_pdu(sock, &clients[idx].addr, &resp);
        return;
    }

    clients[idx].state = STATE_TRANSFER;
    clients[idx].expected_seq = 0;
    resp.data_len = 0;
    printf("[SERVER] WRQ OK de cliente %d, archivo='%s'\n",
           idx, clients[idx].filename);

    (void)send_pdu(sock, &clients[idx].addr, &resp);
}

static void handle_fin(int sock, int idx, const pdu_t *pdu) {
    pdu_t resp = {0};
    resp.type = TYPE_ACK;
    resp.seq  = pdu->seq;

    if (clients[idx].state != STATE_TRANSFER) {
        const char *msg = "FIN fuera de fase";
        memcpy(resp.data, msg, strlen(msg));
        resp.data_len = strlen(msg);
        (void)send_pdu(sock, &clients[idx].addr, &resp);
        return;
    }

    const char *filename = (const char *)pdu->data;
    if (strcmp(filename, clients[idx].filename) != 0) {
        const char *msg = "Filename FIN no coincide";
        memcpy(resp.data, msg, strlen(msg));
        resp.data_len = strlen(msg);
        (void)send_pdu(sock, &clients[idx].addr, &resp);
        return;
    }

    // Cerrar archivo y liberar cliente
    if (clients[idx].fp) {
        fclose(clients[idx].fp);
        clients[idx].fp = NULL;
    }

    clients[idx].state = STATE_FINISHED;
    resp.data_len = 0;
    printf("[SERVER] FIN OK cliente %d, archivo='%s'\n",
           idx, clients[idx].filename);

    (void)send_pdu(sock, &clients[idx].addr, &resp);
    reset_client(idx);
}

static void handle_data(int sock, int idx, const pdu_t *pdu) {
    if (clients[idx].state != STATE_TRANSFER || !clients[idx].fp) {
        fprintf(stderr, "[SERVER] DATA fuera de fase, descarto\n");
        return; // según enunciado: descartar silenciosamente (o log)
    }

    pdu_t resp = {0};
    resp.type = TYPE_ACK;
    resp.seq  = pdu->seq; // ACK eco del seq recibido válido

    if (pdu->seq != clients[idx].expected_seq) {
        fprintf(stderr, "[SERVER] DATA con seq inesperado (recibí %u, esperaba %u)\n",
                pdu->seq, clients[idx].expected_seq);
        // Podrías re-ACKear el último válido; acá solo logueamos
    } else {
        size_t written = fwrite(pdu->data, 1, pdu->data_len, clients[idx].fp);
        if (written != pdu->data_len) {
            perror("fwrite");
        }
        clients[idx].expected_seq ^= 1;
        printf("[SERVER] DATA OK cliente %d, seq=%u, bytes=%zu\n",
               idx, pdu->seq, pdu->data_len);
    }

    (void)send_pdu(sock, &clients[idx].addr, &resp);
}

// ---------- main ----------

int main(void) {
    int sock = socket(AF_INET, SOCK_DGRAM, 0);
    if (sock < 0) {
        perror("socket");
        return EXIT_FAILURE;
    }

    struct sockaddr_in srv_addr;
    memset(&srv_addr, 0, sizeof(srv_addr));
    srv_addr.sin_family      = AF_INET;
    srv_addr.sin_addr.s_addr = htonl(INADDR_ANY);
    srv_addr.sin_port        = htons(SERVER_PORT);

    if (bind(sock, (struct sockaddr *)&srv_addr, sizeof(srv_addr)) < 0) {
        perror("bind");
        close(sock);
        return EXIT_FAILURE;
    }

    printf("[SERVER] Escuchando en UDP puerto %d\n", SERVER_PORT);

    memset(clients, 0, sizeof(clients));

    while (1) {
        struct sockaddr_in cli_addr;
        pdu_t pdu;

        if (recv_pdu(sock, &cli_addr, &pdu) < 0) {
            // error ya logueado
            continue;
        }

        int idx = find_or_create_client(&cli_addr);
        if (idx < 0) {
            fprintf(stderr, "[SERVER] No hay slots libres para clientes\n");
            continue;
        }

        printf("[SERVER] Recibí tipo=%u seq=%u de cliente %d\n",
               pdu.type, pdu.seq, idx);

        switch (pdu.type) {
            case TYPE_HELLO:
                handle_hello(sock, idx, &pdu);
                break;
            case TYPE_WRQ:
                handle_wrq(sock, idx, &pdu);
                break;
            case TYPE_DATA:
                handle_data(sock, idx, &pdu);
                break;
            case TYPE_FIN:
                handle_fin(sock, idx, &pdu);
                break;
            default:
                fprintf(stderr, "[SERVER] Tipo de PDU desconocido %u, descarto\n",
                        pdu.type);
                break;
        }
    }

    close(sock);
    return EXIT_SUCCESS;
}
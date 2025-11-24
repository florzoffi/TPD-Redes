# Makefile para TP UDP Stop & Wait

CC      = gcc
CFLAGS  = -Wall -Wextra -std=c11 -g

# COMMON_SRCS = protocol.c
COMMON_SRCS =

CLIENT_SRCS = udp_client.c $(COMMON_SRCS)
SERVER_SRCS = udp_server.c $(COMMON_SRCS)

CLIENT_BIN  = udp_client
SERVER_BIN  = udp_server

all: $(CLIENT_BIN) $(SERVER_BIN)

$(CLIENT_BIN): $(CLIENT_SRCS)
	$(CC) $(CFLAGS) -o $(CLIENT_BIN) $(CLIENT_SRCS)

$(SERVER_BIN): $(SERVER_SRCS)
	$(CC) $(CFLAGS) -o $(SERVER_BIN) $(SERVER_SRCS)

# Corre el servidor en primer plano
run_server: $(SERVER_BIN)
	./$(SERVER_BIN)

# Corre el cliente contra localhost usando g17.data -> out.data
run_client: $(CLIENT_BIN)
	./$(CLIENT_BIN) 127.0.0.1 g17-d111 g17.data out.data

# Verifica el MD5 del archivo original y del recibido
md5check:
	md5 g17.data
	md5 out.data

clean:
	rm -f $(CLIENT_BIN) $(SERVER_BIN) *.o out.data

.PHONY: all run_server run_client md5check clean

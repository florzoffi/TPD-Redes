CC := gcc
CFLAGS := -Wall -Wextra -std=c11

SRC_DIR := src
INCLUDES := -I$(SRC_DIR)

SERVER_SRCS := $(SRC_DIR)/server.c
CLIENT_SRCS := $(SRC_DIR)/client.c

.PHONY: all clean server client

all: server client

server: $(SERVER_SRCS) $(SRC_DIR)/protocol.h
	$(CC) $(CFLAGS) $(INCLUDES) $(SERVER_SRCS) -o server

server_tester:
	$(CC) $(CFLAGS) $(INCLUDES) -O2 -DTEST_SLOW -o server $(SERVER_SRCS)

client: $(CLIENT_SRCS) $(SRC_DIR)/protocol.h
	$(CC) $(CFLAGS) $(INCLUDES) $(CLIENT_SRCS) -o client

clean:
	rm -f server client

FROM golang:1.24-bullseye AS builder

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends git ca-certificates \
    && rm -rf /var/lib/apt/lists/*

ENV GOPROXY=https://proxy.golang.org,direct \
    GOSUMDB=sum.golang.org \
    GOFLAGS=-buildvcs=false

COPY go.mod go.sum* ./
RUN go mod download

COPY . .
ENV CGO_ENABLED=0
RUN go build -o bigtable-cli .

FROM alpine:latest
RUN apk --no-cache add ca-certificates
WORKDIR /root/
COPY --from=builder /app/bigtable-cli .
CMD ["./bigtable-cli"]

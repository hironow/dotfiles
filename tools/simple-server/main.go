package main

import (
	"log"
	"net/http"
	"os"
	"path/filepath"
)

const HOST = "localhost.hironow.dev"
const PORT = "3000"
const PUBLIC_DIR = "./assets"

func main() {
	// ホームディレクトリのパスを取得
	homeDir, err := os.UserHomeDir()
	if err != nil {
		log.Fatal(err)
	}

	// 証明書と秘密鍵のパス
	certFile := filepath.Join(homeDir, "dotfiles/private/certificates/live/"+HOST+"/fullchain.pem")
	keyFile := filepath.Join(homeDir, "dotfiles/private/certificates/live/"+HOST+"/privkey.pem")

	// 静的ファイルを提供するディレクトリ
	publicDir := PUBLIC_DIR

	// 静的ファイルサーバーを設定
	fs := http.FileServer(http.Dir(publicDir))

	// サーバーのルートで静的ファイルを提供
	http.Handle("/", fs)

	// HTTPSサーバーを起動
	serverAddr := HOST + ":" + PORT
	log.Printf("Starting server at https://%s\n", serverAddr)
	err = http.ListenAndServeTLS(serverAddr, certFile, keyFile, nil)
	if err != nil {
		log.Fatal("Server failed to start: ", err)
	}
}

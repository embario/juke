//go:build windows

package session_test

import "os"

func getFileInfo(path string) (os.FileInfo, error) {
	return os.Stat(path)
}

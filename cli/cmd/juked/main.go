// Command juked is the Juke background daemon.
// It owns the auth token, the IPC socket, and (in later phases) the backend
// connection. Run with --foreground for development; install as a system
// service with the install subcommand once Phase 1 is fully wired.
package main

import (
	"context"
	"fmt"
	"os"

	"github.com/spf13/cobra"

	"github.com/embario/juke/cli/internal/config"
	"github.com/embario/juke/cli/internal/daemon"
	"github.com/embario/juke/cli/internal/daemon/install"
)

func main() {
	if err := rootCmd().Execute(); err != nil {
		fmt.Fprintln(os.Stderr, err)
		os.Exit(1)
	}
}

func rootCmd() *cobra.Command {
	var foreground bool

	root := &cobra.Command{
		Use:   "juked",
		Short: "Juke daemon — manages auth, IPC socket, and backend connection",
		RunE: func(cmd *cobra.Command, _ []string) error {
			paths, err := config.ResolvePaths()
			if err != nil {
				return fmt.Errorf("resolve paths: %w", err)
			}
			d, err := daemon.New(paths)
			if err != nil {
				return err
			}
			if foreground {
				fmt.Fprintln(os.Stderr, "juked: running in foreground (Ctrl+C to stop)")
			}
			return d.Run(context.Background())
		},
	}
	root.Flags().BoolVar(&foreground, "foreground", false,
		"run in the foreground instead of daemonising (useful for development)")

	root.AddCommand(installCmd())
	return root
}

func installCmd() *cobra.Command {
	return &cobra.Command{
		Use:   "install",
		Short: "Install juked as a system service (not yet implemented)",
		RunE: func(cmd *cobra.Command, _ []string) error {
			if err := install.Install(); err != nil {
				return fmt.Errorf("install: %w", err)
			}
			fmt.Fprintln(os.Stdout, "juked service installed successfully.")
			return nil
		},
	}
}

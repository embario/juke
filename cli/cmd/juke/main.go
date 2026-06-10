// Command juke is the Juke interactive terminal UI.
// It connects to the juked daemon over a local IPC socket and renders the
// session status screen (Phase 1). Search, playback, and recommendation panes
// land in Phase 3.
package main

import (
	"fmt"
	"os"

	tea "github.com/charmbracelet/bubbletea"
	"github.com/spf13/cobra"

	"github.com/embario/juke/cli/internal/config"
	"github.com/embario/juke/cli/internal/tui"
)

func main() {
	if err := rootCmd().Execute(); err != nil {
		fmt.Fprintln(os.Stderr, err)
		os.Exit(1)
	}
}

func rootCmd() *cobra.Command {
	return &cobra.Command{
		Use:   "juke",
		Short: "Juke TUI — terminal interface to the Juke music platform",
		RunE: func(cmd *cobra.Command, _ []string) error {
			paths, err := config.ResolvePaths()
			if err != nil {
				return fmt.Errorf("resolve paths: %w", err)
			}
			m := tui.New(paths.Socket)
			p := tea.NewProgram(m, tea.WithAltScreen())
			_, err = p.Run()
			return err
		},
	}
}

import SwiftUI

/// Mac navigation stays beside the content so changing sections never competes
/// with the player. The existing section binding also serves menu shortcuts.
struct JukeSidebar: View {
    @Environment(AppModel.self) private var model
    @Environment(\.jukeTheme) private var theme

    var body: some View {
        VStack(alignment: .leading, spacing: 24) {
            Text("juke")
                .font(JukeFont.wordmark)
                .tracking(-0.5)
                .foregroundStyle(theme.ink.color)
                .padding(.horizontal, 12)
                .padding(.top, 8)
                .accessibilityAddTraits(.isHeader)
            SectionNav(selection: Bindable(model).section)
            Spacer(minLength: 24)
            VStack(alignment: .leading, spacing: 10) {
                Text("Appearance")
                    .font(JukeFont.body(12))
                    .foregroundStyle(theme.sub.color)
                AppearanceControl(choice: Bindable(model.settings).appearance)
                SettingsLink {
                    Label("Settings", systemImage: "gearshape")
                        .font(JukeFont.body(13))
                        .foregroundStyle(theme.ink.color)
                        .frame(maxWidth: .infinity, minHeight: JukeMetrics.minimumHitTarget, alignment: .leading)
                }
                .buttonStyle(.plain)
                .accessibilityIdentifier("sidebar.settings")
            }
            .padding(.horizontal, 12)
        }
        .padding(.horizontal, 12)
        .padding(.vertical, 24)
        .frame(width: 200)
        .frame(maxHeight: .infinity)
        .background(theme.well.color)
        .accessibilityElement(children: .contain)
        .accessibilityLabel("Sidebar")
        .accessibilityIdentifier("navigation.sidebar")
    }
}

/// Sidebar destinations retain their identifiers for the existing UI journeys.
struct SectionNav: View {
    @Binding var selection: JukeSection
    @Environment(\.jukeTheme) private var theme
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    @Namespace private var pill

    var body: some View {
        VStack(spacing: 6) {
            ForEach(JukeSection.allCases) { section in
                let selected = section == selection
                Button {
                    selection = section
                } label: {
                    Label(section.title, systemImage: section.symbol)
                        .font(JukeFont.navLabel)
                        .foregroundStyle(selected ? theme.ink.color : theme.sub.color)
                        .padding(.horizontal, 12)
                        .frame(maxWidth: .infinity, minHeight: JukeMetrics.minimumHitTarget, alignment: .leading)
                        .background {
                            if selected {
                                RoundedRectangle(cornerRadius: 10, style: .continuous)
                                    .fill(theme.card.color)
                                    .shadow(color: .black.opacity(0.14), radius: 1.5, y: 1)
                                    .matchedGeometryEffect(id: "selected", in: pill)
                            }
                        }
                        .contentShape(Rectangle())
                }
                .buttonStyle(.plain)
                .accessibilityIdentifier("nav.\(section.rawValue)")
                .accessibilityAddTraits(selected ? .isSelected : [])
            }
        }
        .animation(JukeMotion.control(reduceMotion: reduceMotion), value: selection)
        .accessibilityElement(children: .contain)
        .accessibilityLabel("Sections")
    }
}

/// Match system / Light / Dark.
struct AppearanceControl: View {
    @Binding var choice: AppearanceChoice
    @Environment(\.jukeTheme) private var theme

    var body: some View {
        HStack(spacing: 2) {
            ForEach(AppearanceChoice.allCases) { option in
                let selected = option == choice
                Button {
                    choice = option
                } label: {
                    Image(systemName: option.symbol)
                        .font(.system(size: 16, weight: .medium))
                        .foregroundStyle(selected ? theme.ink.color : theme.sub.color)
                        .frame(width: JukeMetrics.minimumHitTarget, height: JukeMetrics.minimumHitTarget)
                        .background(selected ? theme.card.color : .clear, in: Circle())
                        .contentShape(Circle())
                }
                .buttonStyle(.plain)
                .help(option.label)
                .accessibilityLabel(option.label)
                .accessibilityAddTraits(selected ? .isSelected : [])
                .accessibilityIdentifier("appearance.\(option.rawValue)")
            }
        }
        .padding(4)
        .background(theme.well.color, in: Capsule())
        .accessibilityElement(children: .contain)
        .accessibilityLabel("Appearance")
    }
}

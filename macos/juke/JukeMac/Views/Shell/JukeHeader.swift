import SwiftUI

/// The window header: "juke" wordmark, the centred section nav, and the
/// appearance control. Layout and sizes follow the design reference.
struct JukeHeader: View {
    @Environment(AppModel.self) private var model
    @Environment(\.jukeTheme) private var theme

    var body: some View {
        HStack(spacing: 0) {
            Text("juke")
                .font(JukeFont.wordmark)
                .tracking(-0.5)
                .foregroundStyle(theme.ink.color)
                .frame(width: JukeMetrics.headerSideWidth, alignment: .leading)
                .accessibilityAddTraits(.isHeader)
            Spacer(minLength: 12)
            SectionNav(selection: Bindable(model).section)
            Spacer(minLength: 12)
            AppearanceControl(choice: Bindable(model.settings).appearance)
                .frame(width: JukeMetrics.headerSideWidth, alignment: .trailing)
        }
        .padding(.horizontal, JukeMetrics.headerHorizontalPadding)
        .padding(.vertical, JukeMetrics.headerVerticalPadding)
    }
}

/// Radio · Library · Memories · Chat. The selected tab sits on a card-coloured
/// pill inside the well, as in the prototype.
struct SectionNav: View {
    @Binding var selection: JukeSection
    @Environment(\.jukeTheme) private var theme
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    @Namespace private var pill

    var body: some View {
        HStack(spacing: 4) {
            ForEach(JukeSection.allCases) { section in
                let selected = section == selection
                Button {
                    selection = section
                } label: {
                    Text(section.title)
                        .font(JukeFont.navLabel)
                        .foregroundStyle(selected ? theme.ink.color : theme.sub.color)
                        .padding(.horizontal, 22)
                        .frame(minHeight: JukeMetrics.minimumHitTarget)
                        .background {
                            if selected {
                                Capsule()
                                    .fill(theme.card.color)
                                    .shadow(color: .black.opacity(0.14), radius: 1.5, y: 1)
                                    .matchedGeometryEffect(id: "selected", in: pill)
                            }
                        }
                        .contentShape(Capsule())
                }
                .buttonStyle(.plain)
                .accessibilityIdentifier("nav.\(section.rawValue)")
                .accessibilityAddTraits(selected ? .isSelected : [])
            }
        }
        .padding(4)
        .background(theme.well.color, in: Capsule())
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

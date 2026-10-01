import SwiftUI

/// New Station flow (Records or Feelings first, the other step optional).
/// Placeholder owned by S4; RadioScreen shows it for `JukeCoordinator.RadioRoute.newStation`.
struct NewStationScreen: View {
    @Environment(AppModel.self) private var model
    let draft: JukeCoordinator.NewStationDraft

    var body: some View {
        JukeCard {
            VStack(alignment: .leading, spacing: 12) {
                Text("New station").font(JukeFont.display(24, weight: .bold))
                Button("Back to Radio") { model.coordinator.closeNewStation() }
                    .buttonStyle(JukeWellButtonStyle())
            }
        }
        .accessibilityIdentifier("newStation.screen")
    }
}

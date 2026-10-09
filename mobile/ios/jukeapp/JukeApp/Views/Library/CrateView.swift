import SwiftUI

/// Flip through records like a crate: drag along the axis, release to settle.
/// Tap the front record to open it.
struct CrateView: View {
    let items: [Radio.CrateItem]
    let mode: CrateMode
    let onSelect: (Radio.CrateItem) -> Void
    @Binding var focus: Int
    /// Resets by itself if the system cancels the gesture.
    @GestureState private var dragDelta: CGFloat = 0

    var body: some View {
        let position = CrateLayout.position(focus: focus, dragDelta: dragDelta, mode: mode)
        ZStack {
            ForEach(CrateLayout.visibleIndices(focus: Int(position.rounded()), count: items.count), id: \.self) { index in
                let t = CrateLayout.transform(index: index, position: position, mode: mode)
                Sleeve(item: items[index])
                    .frame(width: mode.sleeveSize, height: mode.sleeveSize)
                    .brightness(t.brightness - 1)
                    .scaleEffect(t.scale)
                    .rotation3DEffect(.degrees(t.rotationX), axis: (1, 0, 0), perspective: 0.6)
                    .rotation3DEffect(.degrees(t.rotationY), axis: (0, 1, 0), perspective: 0.6)
                    .offset(x: t.x, y: t.y)
                    .opacity(t.opacity)
                    .zIndex(t.zIndex)
                    .onTapGesture { if index == focus { onSelect(items[index]) } else { withAnimation(.smooth(duration: CrateLayout.settleDuration)) { focus = index } } }
            }
        }
        .frame(maxWidth: .infinity).frame(height: CrateLayout.wellHeight + 40)
        .contentShape(Rectangle())
        .gesture(DragGesture(minimumDistance: CrateLayout.dragThreshold)
            .updating($dragDelta) { value, state, _ in state = axis(value.translation) }
            .onEnded { value in
                let velocity = axis(CGSize(width: value.velocity.width, height: value.velocity.height)) / 1000
                let next = CrateLayout.releasedFocus(focus: focus, count: items.count, dragDelta: axis(value.translation), velocity: velocity, mode: mode)
                withAnimation(.smooth(duration: CrateLayout.settleDuration)) { focus = next }
            })
        .sensoryFeedback(.selection, trigger: focus)
        .accessibilityElement(children: .ignore)
        .accessibilityLabel(items.indices.contains(focus) ? "\(items[focus].title), record \(focus + 1) of \(items.count)" : "Empty crate")
        .accessibilityIdentifier("library.crate")
        .accessibilityAdjustableAction { direction in
            focus = CrateLayout.clamp(focus + (direction == .increment ? 1 : -1), count: items.count)
        }
    }

    private func axis(_ size: CGSize) -> CGFloat { mode == .frontToBack ? size.height : size.width }

    private struct Sleeve: View {
        let item: Radio.CrateItem
        var body: some View {
            AsyncImage(url: item.artworkURL) { $0.resizable().scaledToFill() } placeholder: {
                ZStack { Color.secondary.opacity(0.2); Image(systemName: "music.note").foregroundStyle(.secondary) }
            }
            .clipShape(RoundedRectangle(cornerRadius: 10, style: .continuous))
            .shadow(color: .black.opacity(0.3), radius: 8, y: 5)
        }
    }
}

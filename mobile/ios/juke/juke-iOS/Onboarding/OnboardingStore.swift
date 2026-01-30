import Foundation

@MainActor
final class OnboardingStore: ObservableObject {
    @Published private(set) var currentStep: OnboardingStep = .genres
    @Published private(set) var data: OnboardingData
    @Published var isSubmitting = false
    @Published var error: String?

    private let defaults: UserDefaults
    private let userKey: String?

    private let steps = OnboardingStep.allCases

    var currentStepIndex: Int {
        steps.firstIndex(of: currentStep) ?? 0
    }

    var totalSteps: Int { steps.count }

    var progress: Double {
        Double(currentStepIndex + 1) / Double(totalSteps) * 100
    }

    var canGoBack: Bool {
        currentStepIndex > 0
    }

    var canGoNext: Bool {
        currentStepIndex < totalSteps - 1
    }

    init(userKey: String? = nil, defaults: UserDefaults = .standard) {
        self.defaults = defaults
        self.userKey = userKey
        self.data = OnboardingStore.loadDraft(from: defaults, userKey: userKey) ?? OnboardingData()
    }

    // MARK: - Navigation

    func goNext() {
        guard canGoNext else { return }
        currentStep = steps[currentStepIndex + 1]
        saveDraft()
    }

    func goBack() {
        guard canGoBack else { return }
        currentStep = steps[currentStepIndex - 1]
    }

    func restart() {
        data = OnboardingData()
        currentStep = .genres
        clearDraft()
    }

    // MARK: - Data updates

    func setFavoriteGenres(_ genres: [String]) {
        data.favoriteGenres = genres
        saveDraft()
    }

    func toggleFavoriteGenre(_ genreId: String) {
        if data.favoriteGenres.contains(genreId) {
            data.favoriteGenres.removeAll { $0 == genreId }
        } else if data.favoriteGenres.count < 3 {
            data.favoriteGenres.append(genreId)
        }
        saveDraft()
    }

    func setRideOrDieArtist(_ artist: OnboardingArtist?) {
        data.rideOrDieArtist = artist
        saveDraft()
    }

    func toggleHatedGenre(_ genreId: String) {
        if data.hatedGenres.contains(genreId) {
            data.hatedGenres.removeAll { $0 == genreId }
        } else if data.hatedGenres.count < 3 {
            data.hatedGenres.append(genreId)
        }
        saveDraft()
    }

    func setRainyDayMood(_ mood: String?) {
        data.rainyDayMood = mood
        saveDraft()
    }

    func setWorkoutVibe(_ vibe: String?) {
        data.workoutVibe = vibe
        saveDraft()
    }

    func setFavoriteDecade(_ decade: String?) {
        data.favoriteDecade = decade
        saveDraft()
    }

    func setListeningStyle(_ style: String?) {
        data.listeningStyle = style
        saveDraft()
    }

    func setAgeRange(_ range: String?) {
        data.ageRange = range
        saveDraft()
    }

    func setLocation(_ city: CityLocation?) {
        data.location = city
        saveDraft()
    }

    // MARK: - Persistence

    private func saveDraft() {
        guard data.completedAt == nil else { return }
        if let encoded = try? JSONEncoder().encode(data) {
            defaults.set(encoded, forKey: draftKey())
        }
    }

    func clearDraft() {
        defaults.removeObject(forKey: draftKey())
    }

    // MARK: - Completion check

    private static let completedKey = "juke-onboarding-completed"

    private func draftKey() -> String {
        guard let userKey else { return "juke-onboarding-draft" }
        return "juke-onboarding-draft-\(userKey)"
    }

    private static func completedKey(for userKey: String?) -> String {
        guard let userKey else { return completedKey }
        return "\(completedKey)-\(userKey)"
    }

    static func isCompleted(for userKey: String?, defaults: UserDefaults = .standard) -> Bool {
        defaults.bool(forKey: completedKey(for: userKey))
    }

    func markCompleted() {
        defaults.set(true, forKey: OnboardingStore.completedKey(for: userKey))
        clearDraft()
    }

    private static func loadDraft(from defaults: UserDefaults, userKey: String?) -> OnboardingData? {
        if defaults.bool(forKey: completedKey(for: userKey)) { return nil }
        let key = userKey == nil ? "juke-onboarding-draft" : "juke-onboarding-draft-\(userKey!)"
        guard let encoded = defaults.data(forKey: key) else { return nil }
        let data = try? JSONDecoder().decode(OnboardingData.self, from: encoded)
        if data?.completedAt != nil { return nil }
        return data
    }
}

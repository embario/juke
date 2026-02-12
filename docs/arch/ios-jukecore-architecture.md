# JukeCore iOS Library - Architecture Document

## Executive Summary

This document outlines the architecture for **JukeCore**, a shared Swift Package that will encapsulate common and reusable components across all Juke iOS applications (Juke, ShotClock, and TuneTrivia). This refactoring will eliminate code duplication, ensure consistent behavior, and reduce maintenance overhead.

---

## Current State Analysis

### Code Distribution (Source Files Only)

| App | Swift Files | Approximate Lines |
|-----|-------------|-------------------|
| Juke | 22 | ~1,900 |
| ShotClock | 27 | ~2,800 |
| TuneTrivia | 19 | ~3,800 |
| **Total** | **68** | **~8,500** |

### Identified Duplication Categories

After auditing all three apps, the following areas of significant code duplication were identified:

---

## 1. Networking Layer (HIGH DUPLICATION)

### Current State

Each app has its own `APIClient.swift` with nearly identical implementations:

| Component | Juke | ShotClock | TuneTrivia |
|-----------|------|-----------|------------|
| APIConfiguration | ✅ (34 lines) | ❌ (inline) | ✅ (34 lines) |
| HTTPMethod enum | ✅ (7 lines) | ❌ (strings) | ✅ (8 lines) |
| APIError enum | ✅ (18 lines) | ✅ (28 lines) | ✅ (19 lines) |
| APIClient class | ✅ (182 lines) | ✅ (167 lines) | ✅ (192 lines) |
| ISO8601 Date Formatters | ✅ (4 formatters) | ✅ (2 formatters) | ✅ (3 formatters) |

**Common Functionality:**
- URL building with path normalization
- Authorization header injection (`Token <token>`)
- JSON encoding/decoding with snake_case conversion
- ISO8601 date parsing (multiple format fallbacks)
- Error message extraction from JSON responses
- Detailed logging for debugging

**Variations:**
- Juke/TuneTrivia use `send()` generic method
- ShotClock uses typed methods (`get()`, `post()`, `patch()`, `delete()`)
- Juke has `frontendURL` for deep-link support
- ShotClock has `AnyEncodable` wrapper

### Proposed JukeCore Design

```swift
// JukeCore/Sources/JukeCore/Networking/

public struct JukeAPIConfiguration {
    public let baseURL: URL
    public let frontendURL: URL?

    public init(bundle: Bundle, processInfo: ProcessInfo)
    public init(baseURL: URL, frontendURL: URL?)
}

public enum JukeHTTPMethod: String {
    case get, post, patch, put, delete
}

public enum JukeAPIError: LocalizedError {
    case invalidURL
    case invalidResponse
    case unauthorized
    case server(status: Int, message: String)
    case decoding(Error)
    case networkError(Error)
}

public final class JukeAPIClient {
    public static let shared: JukeAPIClient

    // Generic send method (preferred)
    public func send<T: Decodable>(_ path: String, method: JukeHTTPMethod, token: String?, queryItems: [URLQueryItem]?, body: Data?) async throws -> T

    // Empty response variant
    public func sendEmpty(_ path: String, method: JukeHTTPMethod, token: String?, body: Data?) async throws

    // Typed convenience methods
    public func get<T: Decodable>(_ path: String, token: String?, queryItems: [URLQueryItem]?) async throws -> T
    public func post<T: Decodable>(_ path: String, body: Encodable?, token: String?) async throws -> T
    public func patch<T: Decodable>(_ path: String, body: Encodable?, token: String?) async throws -> T
    public func delete(_ path: String, token: String?) async throws
}

// Date parsing utilities
public struct JukeDateParsing {
    public static func parseISO8601(_ string: String) -> Date?
    public static var iso8601Decoder: JSONDecoder
}
```

**Estimated Savings:** ~400 lines removed across all apps

---

## 2. Authentication System (HIGH DUPLICATION)

### Current State

| Component | Juke | ShotClock | TuneTrivia |
|-----------|------|-----------|------------|
| AuthService | ✅ (110 lines) | ✅ (35 lines) | ✅ (67 lines) |
| AuthTokenResponse | ✅ | ✅ (TokenResponse) | ✅ |
| LoginRequest | ✅ | ✅ | ✅ |
| RegisterRequest | ✅ | ✅ | ✅ |
| RegisterResponse | ✅ | ✅ | ✅ |
| VerifyRegistrationRequest | ✅ | ✅ | ❌ |
| AppConfiguration | ✅ (30 lines) | ✅ (30 lines) | ❌ |

**Common Functionality:**
- Login with username/password → token
- Register with username/email/password
- Verify email registration (deep link)
- Resend verification email (Juke only)
- Logout with server-side session revocation
- Registration disabled flag from environment/plist

### Proposed JukeCore Design

```swift
// JukeCore/Sources/JukeCore/Auth/

// MARK: - Models
public struct JukeAuthTokenResponse: Decodable {
    public let token: String
}

public struct JukeLoginRequest: Encodable {
    public let username: String
    public let password: String
}

public struct JukeRegisterRequest: Encodable {
    public let username: String
    public let email: String
    public let password: String
    public let passwordConfirm: String
}

public struct JukeRegisterResponse: Decodable {
    public let detail: String?
}

public struct JukeVerifyRegistrationRequest: Encodable {
    public let userId: String
    public let timestamp: String
    public let signature: String
}

// MARK: - Service
public final class JukeAuthService {
    public init(client: JukeAPIClient)

    public func login(username: String, password: String) async throws -> String
    public func register(username: String, email: String, password: String, passwordConfirm: String) async throws -> JukeRegisterResponse
    public func logout(token: String) async throws
    public func verifyRegistration(userId: String, timestamp: String, signature: String) async throws
    public func resendVerification(email: String) async throws -> JukeRegisterResponse
}

// MARK: - Configuration
public struct JukeAppConfiguration {
    public static let shared: JukeAppConfiguration
    public let isRegistrationDisabled: Bool

    public init(bundle: Bundle, processInfo: ProcessInfo)
}
```

**Estimated Savings:** ~180 lines removed across all apps

---

## 3. Session State Management (HIGH DUPLICATION)

### Current State

Each app has a `SessionStore.swift` with nearly identical authentication state management:

| Feature | Juke | ShotClock | TuneTrivia |
|---------|------|-----------|------------|
| Token persistence | ✅ UserDefaults | ✅ UserDefaults | ✅ UserDefaults |
| Profile fetching | ✅ | ✅ | ✅ |
| Login flow | ✅ | ✅ | ✅ |
| Registration flow | ✅ | ❌ (delegate to VM) | ✅ |
| Token validation on launch | ✅ (401/403 logout) | ✅ (unauthorized logout) | ❌ |
| Server-side logout | ✅ | ❌ | ❌ |

**Variations:**
- Key prefixes differ (`juke.auth.token`, `shotclock.auth.token`, `tunetrivia.auth.token`)
- Juke stores username separately
- Juke has `validateAndRefreshProfile()` for stale token detection
- ShotClock has `verificationMessage` for deep-link result display

### Proposed JukeCore Design

```swift
// JukeCore/Sources/JukeCore/Session/

public protocol JukeSessionStoreDelegate: AnyObject {
    /// Called when authentication state changes.
    func sessionStoreDidUpdateAuthState(_ store: JukeSessionStore)
    /// Called when the user profile is refreshed.
    func sessionStore(_ store: JukeSessionStore, didUpdateProfile profile: JukeMusicProfile?)
}

@MainActor
public class JukeSessionStore: ObservableObject {
    @Published public private(set) var token: String?
    @Published public private(set) var username: String?
    @Published public private(set) var profile: JukeMusicProfile?
    @Published public private(set) var isLoadingProfile: Bool

    public weak var delegate: JukeSessionStoreDelegate?

    public init(
        keyPrefix: String,  // e.g., "juke", "shotclock", "tunetrivia"
        authService: JukeAuthService,
        profileService: JukeProfileService,
        defaults: UserDefaults
    )

    public var isAuthenticated: Bool { token != nil }

    // Auth operations
    public func login(username: String, password: String) async throws
    public func register(username: String, email: String, password: String, passwordConfirm: String) async throws -> String
    public func authenticateWithToken(_ token: String, username: String?)
    public func logout()

    // Profile operations
    public func refreshProfile() async throws

    // Token validation
    public func validateStoredToken() async
}
```

**Estimated Savings:** ~170 lines removed across all apps

---

## 4. User/Profile Models (MEDIUM DUPLICATION)

### Current State

| Model | Juke | ShotClock | TuneTrivia |
|-------|------|-----------|------------|
| MusicProfile | ✅ (82 lines) | ❌ | ✅ (35 lines) |
| UserProfile | ❌ | ✅ (14 lines) | ❌ |
| User | ❌ | ❌ | ✅ (31 lines) |
| MusicProfileSummary | ✅ (38 lines) | ❌ | ❌ |

**Analysis:**
- Juke has the most complete `MusicProfile` with custom decoder for optional fields
- ShotClock's `UserProfile` is simpler but overlaps
- TuneTrivia has both `User` and `MusicProfile`

### Proposed JukeCore Design

```swift
// JukeCore/Sources/JukeCore/Models/

public struct JukeUser: Codable, Identifiable {
    public let id: Int
    public let username: String
    public let email: String?
    public let firstName: String?
    public let lastName: String?

    public var displayName: String { ... }
}

public struct JukeMusicProfile: Codable, Identifiable {
    public let id: Int
    public let username: String
    public let name: String?
    public let displayName: String?
    public let tagline: String?
    public let bio: String?
    public let location: String?
    public let avatarURL: URL?
    public let favoriteGenres: [String]
    public let favoriteArtists: [String]
    public let favoriteAlbums: [String]
    public let favoriteTracks: [String]
    public let onboardingCompletedAt: Date?
    public let createdAt: Date?
    public let modifiedAt: Date?
    public let isOwner: Bool

    public var preferredName: String { ... }
}

public struct JukeMusicProfileSummary: Codable, Identifiable {
    public let username: String
    public let displayName: String?
    public let tagline: String?
    public let avatarURL: URL?
}

public struct JukeProfileService {
    public func fetchMyProfile(token: String) async throws -> JukeMusicProfile
    public func fetchProfile(username: String, token: String) async throws -> JukeMusicProfile
    public func searchProfiles(token: String, query: String) async throws -> [JukeMusicProfileSummary]
}

public struct JukePaginatedResponse<T: Decodable>: Decodable {
    public let results: [T]
    public let count: Int?
    public let next: String?
    public let previous: String?
}
```

**Estimated Savings:** ~120 lines removed across all apps

---

## 5. Design System Components (MEDIUM DUPLICATION)

### Current State

Each app has its own design system with structurally identical but visually different components:

| Component | Juke | ShotClock | TuneTrivia |
|-----------|------|-----------|------------|
| Color Palette | ✅ JukePalette | ✅ SCPalette | ✅ TuneTriviaPalette |
| Color(hex:) extension | ✅ | ✅ | ✅ |
| Background View | ✅ JukeBackground | ✅ SCBackground | ✅ TuneTriviaBackground |
| Card View | ✅ JukeCard | ✅ SCCard | ✅ TuneTriviaCard |
| Button Style | ✅ JukeButtonStyle | ✅ SCButtonStyle | ✅ TuneTriviaButtonStyle |
| Input Field | ✅ JukeInputField | ✅ SCInputField | ✅ TuneTriviaInputField |
| Status Banner | ✅ JukeStatusBanner | ✅ SCStatusBanner | ✅ TuneTriviaStatusBanner |
| Spinner | ✅ JukeSpinner | ✅ SCSpinner | ✅ TuneTriviaSpinner |
| Chip | ✅ JukeChip | ✅ SCChip | ✅ TuneTriviaChip |

**Analysis:**
The structural implementation is identical, but colors differ by brand. The solution is to create a **themeable design system** with protocol-based palette injection.

### Proposed JukeCore Design

```swift
// JukeCore/Sources/JukeCore/DesignSystem/

// MARK: - Theme Protocol
public protocol JukeTheme {
    var background: Color { get }
    var panel: Color { get }
    var panelAlt: Color { get }
    var accent: Color { get }
    var accentSoft: Color { get }
    var secondary: Color { get }
    var text: Color { get }
    var muted: Color { get }
    var border: Color { get }
    var success: Color { get }
    var warning: Color { get }
    var error: Color { get }
}

// MARK: - Built-in Themes
public struct JukeDefaultTheme: JukeTheme { ... }
public struct ShotClockTheme: JukeTheme { ... }
public struct TuneTriviaTheme: JukeTheme { ... }

// MARK: - Theme Environment
public struct JukeThemeKey: EnvironmentKey {
    public static let defaultValue: JukeTheme = JukeDefaultTheme()
}

extension EnvironmentValues {
    public var jukeTheme: JukeTheme { ... }
}

// MARK: - Components
public struct JukeCoreBackground<Theme: JukeTheme>: View { ... }
public struct JukeCoreCard<Content: View>: View { ... }
public struct JukeCoreButtonStyle: ButtonStyle { ... }
public struct JukeCoreInputField: View { ... }
public struct JukeCoreStatusBanner: View { ... }
public struct JukeCoreSpinner: View { ... }
public struct JukeCoreChip: View { ... }

// MARK: - Utilities
extension Color {
    public init(hex: String)
}
```

**Estimated Savings:** ~500 lines removed across all apps

---

## 6. Deep Link Handling (MEDIUM DUPLICATION)

### Current State

| Feature | Juke | ShotClock | TuneTrivia |
|---------|------|-----------|------------|
| Email verification deep link | ✅ | ✅ | ❌ |
| URLComponents.queryParameters | ✅ | ❌ | ❌ |
| Spotify callback handling | ❌ | ✅ | ❌ |
| Universal link support | ✅ | ❌ | ❌ |

### Proposed JukeCore Design

```swift
// JukeCore/Sources/JukeCore/DeepLink/

public enum JukeDeepLink {
    case verifyUser(userId: String, timestamp: String, signature: String)
    case register  // Opens native Juke app for registration
    case custom(host: String, path: String, queryItems: [URLQueryItem])
}

public struct JukeDeepLinkParser {
    public let supportedSchemes: [String]
    public let universalLinkHosts: [String]

    public init(schemes: [String], hosts: [String])

    public func parse(_ url: URL) -> JukeDeepLink?
}

public struct JukeDeepLinkHandler {
    public static func handleVerification(
        userId: String,
        timestamp: String,
        signature: String,
        authService: JukeAuthService
    ) async throws

    public static func openJukeAppForRegistration() -> Bool
}

extension URLComponents {
    public var queryParameters: [String: String] { ... }
}
```

**Estimated Savings:** ~80 lines removed across apps

---

## 7. AuthViewModel (MEDIUM DUPLICATION)

### Current State

| Feature | Juke | ShotClock | TuneTrivia |
|---------|------|-----------|------------|
| AuthViewModel | ✅ (109 lines) | ✅ (96 lines) | ❌ (inline in View) |
| Form validation | ✅ | ✅ | ✅ |
| Registration disabled check | ✅ | ✅ | ❌ |
| Resend verification | ✅ | ❌ | ❌ |

### Proposed JukeCore Design

```swift
// JukeCore/Sources/JukeCore/ViewModels/

@MainActor
public class JukeAuthViewModel: ObservableObject {
    @Published public var username: String = ""
    @Published public var email: String = ""
    @Published public var password: String = ""
    @Published public var passwordConfirm: String = ""
    @Published public var isRegistering: Bool = false
    @Published public var isLoading: Bool = false
    @Published public var errorMessage: String?
    @Published public var successMessage: String?
    @Published public var showResendAction: Bool = false
    @Published public var isResending: Bool = false
    @Published public var resendMessage: String?
    @Published public var resendError: String?

    public var isRegistrationDisabled: Bool { ... }

    public init(session: JukeSessionStore, configuration: JukeAppConfiguration)

    public func setMode(registering: Bool)
    public func submit() async
    public func resendVerification() async
}
```

**Estimated Savings:** ~150 lines removed across apps

---

## Summary of Extraction

### Components to Extract into JukeCore

| Category | Components | Est. Lines Saved |
|----------|------------|------------------|
| Networking | APIConfiguration, HTTPMethod, APIError, APIClient, DateParsing | 400 |
| Auth | AuthService, Auth models, AppConfiguration | 180 |
| Session | SessionStore, SessionStoreDelegate | 170 |
| Models | User, MusicProfile, MusicProfileSummary, PaginatedResponse, ProfileService | 120 |
| Design System | Theme protocol, Color extension, Card, Button, Input, Banner, Spinner, Chip | 500 |
| Deep Links | DeepLinkParser, DeepLinkHandler, URLComponents extension | 80 |
| ViewModels | AuthViewModel | 150 |
| **Total** | | **~1,600 lines** |

### Estimated Impact

| App | Current Lines | After Refactor | Reduction |
|-----|---------------|----------------|-----------|
| Juke | ~1,900 | ~1,350 | ~550 lines (29%) |
| ShotClock | ~2,800 | ~2,250 | ~550 lines (20%) |
| TuneTrivia | ~3,800 | ~3,300 | ~500 lines (13%) |

---

## Implementation Plan

### Phase 1: Create JukeCore Swift Package
1. Create `mobile/ios/Packages/JukeCore/` directory
2. Initialize Swift Package with `Package.swift` (minimum iOS 16.0)
3. Set up folder structure:
   ```
   Packages/JukeCore/
   ├── Package.swift
   ├── Sources/
   │   └── JukeCore/
   │       ├── Networking/
   │       ├── Auth/
   │       ├── Session/
   │       ├── Models/
   │       ├── DesignSystem/
   │       ├── DeepLink/
   │       └── ViewModels/
   └── Tests/
       └── JukeCoreTests/
   ```

### Phase 2: Extract Networking Layer
- Extract `JukeAPIClient`, `JukeAPIConfiguration`, `JukeAPIError`, `JukeHTTPMethod`
- Migrate all three apps to use JukeCore networking
- Remove duplicate code from each app

### Phase 3: Extract Authentication
- Extract `JukeAuthService`, auth models, `JukeAppConfiguration`
- Migrate all three apps
- Remove duplicate code

### Phase 4: Extract Session Management
- Extract `JukeSessionStore` with delegate protocol
- Migrate apps with app-specific key prefixes
- Remove duplicate code

### Phase 5: Extract Models
- Extract `JukeMusicProfile`, `JukeUser`, `JukeProfileService`
- Migrate apps
- Remove duplicate code

### Phase 6: Extract Design System
- Extract themeable components
- Create app-specific theme implementations
- Migrate apps using theme injection
- Remove duplicate design system code

### Phase 7: Extract Deep Links & ViewModels
- Extract `JukeDeepLinkParser`, `JukeAuthViewModel`
- Migrate apps
- Final cleanup

---

## Refactoring Log

| Phase | App | Files Modified | Lines Removed | Status |
|-------|-----|----------------|---------------|--------|
| 1 | - | Package.swift created | 0 | Pending |
| 2 | Juke | TBD | TBD | Pending |
| 2 | ShotClock | TBD | TBD | Pending |
| 2 | TuneTrivia | TBD | TBD | Pending |
| 3 | Juke | TBD | TBD | Pending |
| 3 | ShotClock | TBD | TBD | Pending |
| 3 | TuneTrivia | TBD | TBD | Pending |
| ... | ... | ... | ... | ... |

---

## Registration Deep-Link Requirement

Per the acceptance criteria, apps like ShotClock and TuneTrivia should support redirecting users to register using the native Juke app. If the Juke app is not installed, it will fall back to opening the web registration page via `FRONTEND_URL`.

```swift
public struct JukeDeepLinkHandler {
    /// Opens the native Juke app's registration flow.
    /// Falls back to web registration if Juke app is not installed.
    /// - Parameter frontendURL: The FRONTEND_URL for web fallback
    /// - Returns: true if either the app or web URL was opened successfully
    @MainActor
    public static func openRegistration(frontendURL: URL?) -> Bool {
        // Try native Juke app first
        if let jukeURL = URL(string: "juke://register"),
           UIApplication.shared.canOpenURL(jukeURL) {
            UIApplication.shared.open(jukeURL)
            return true
        }

        // Fall back to web registration
        if let webURL = frontendURL?.appendingPathComponent("register") {
            UIApplication.shared.open(webURL)
            return true
        }

        return false
    }
}
```

This allows satellite apps (ShotClock, TuneTrivia) to delegate registration to the main Juke app while still supporting login locally, with a web fallback when the native app isn't installed.

---

## Next Steps

1. **Review & Approve** this architecture document
2. **Create JukeCore Package** (Phase 1)
3. **Iteratively extract** each component, testing after each phase
4. **Update this document** with actual line counts as work progresses

---

*Document Version: 1.0*
*Last Updated: 2026-02-11*
*Author: Claude (AI Assistant)*

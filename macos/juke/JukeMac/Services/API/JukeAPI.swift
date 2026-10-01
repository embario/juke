import Foundation
import Synchronization

/// Errors from `JukeAPI`, mapped from HTTP status codes and transport failures.
enum JukeAPIError: LocalizedError, Equatable, Sendable {
    case notSignedIn
    case unauthorized
    case forbidden
    case notFound
    /// 400 or 409/422: the server rejected the request. `message` is the first
    /// human-readable detail the server returned, when there is one.
    case rejected(status: Int, message: String?)
    case server(status: Int)
    case transport(String)
    case decoding(String)
    case responseTooLarge

    var errorDescription: String? {
        switch self {
        case .notSignedIn: "Sign in to Juke first."
        case .unauthorized: "Your Juke session has expired. Sign in again."
        case .forbidden: "This Juke account cannot do that."
        case .notFound: "Juke could not find that."
        case .rejected(_, let message): message ?? "Juke could not accept that request."
        case .server: "Juke is temporarily unavailable. Try again in a moment."
        case .transport: "Juke could not be reached. Check your connection or the server in Settings."
        case .decoding: "Juke sent a response this version of the app does not understand."
        case .responseTooLarge: "Juke sent an unexpectedly large response."
        }
    }

    /// Maps a non-2xx status to an error, reading DRF-style `detail` or field
    /// errors from the body when present.
    static func from(status: Int, body: Data) -> JukeAPIError {
        switch status {
        case 401: return .unauthorized
        case 403: return .forbidden
        case 404: return .notFound
        case 400, 409, 422: return .rejected(status: status, message: serverMessage(in: body))
        default: return .server(status: status)
        }
    }

    private static func serverMessage(in body: Data) -> String? {
        guard let object = try? JSONSerialization.jsonObject(with: body) else { return nil }
        if let dictionary = object as? [String: Any] {
            if let detail = dictionary["detail"] as? String { return detail }
            for key in dictionary.keys.sorted() {
                if let text = dictionary[key] as? String { return text }
                if let list = dictionary[key] as? [String], let first = list.first { return first }
            }
        }
        if let list = object as? [String] { return list.first }
        return nil
    }
}

enum HTTPMethod: String, Sendable {
    case get = "GET", post = "POST", put = "PUT", patch = "PATCH", delete = "DELETE"
}

/// Shared, typed HTTP client for the Juke REST API.
///
/// - Base URL: resolved per request from `JukeServer` (the Settings value)
///   unless a fixed one is injected for tests.
/// - Auth: `Authorization: Token <token>`, the scheme every Juke endpoint accepts.
/// - JSON: keys are used as declared (the radio and Vibe APIs are camelCase);
///   dates are ISO 8601 with or without fractional seconds.
///
/// Screens get one from `AppModel.api`; endpoint methods live in extensions
/// (see `JukeAPI+Radio.swift`).
struct JukeAPI: Sendable {
    typealias TokenProvider = @Sendable () async -> String?

    private let fixedBaseURL: URL?
    private let token: TokenProvider
    private let session: URLSession
    private let maxResponseBytes: Int

    init(baseURL: URL? = nil, session: URLSession? = nil, maxResponseBytes: Int = 4_000_000, token: @escaping TokenProvider) {
        fixedBaseURL = baseURL
        self.token = token
        self.maxResponseBytes = maxResponseBytes
        if let session {
            self.session = session
        } else {
            let configuration = URLSessionConfiguration.ephemeral
            configuration.timeoutIntervalForRequest = 20
            configuration.requestCachePolicy = .reloadIgnoringLocalCacheData
            self.session = URLSession(configuration: configuration)
        }
    }

    /// `<base>/api/v1/`.
    var apiURL: URL { fixedBaseURL.map { $0.appending(path: "api/v1/") } ?? JukeServer.apiURL() }

    // MARK: Request helpers

    func get<Response: Decodable>(_ path: String, query: [URLQueryItem] = [], as type: Response.Type = Response.self) async throws -> Response {
        try decode(Response.self, from: try await perform(.get, path, query: query, body: nil))
    }

    func send<Body: Encodable, Response: Decodable>(_ method: HTTPMethod, _ path: String, body: Body, as type: Response.Type = Response.self) async throws -> Response {
        try decode(Response.self, from: try await perform(method, path, query: [], body: try Self.encoder.encode(body)))
    }

    /// For endpoints that answer 204 No Content.
    func sendExpectingNoContent<Body: Encodable>(_ method: HTTPMethod, _ path: String, body: Body) async throws {
        _ = try await perform(method, path, query: [], body: try Self.encoder.encode(body))
    }

    func delete(_ path: String) async throws {
        _ = try await perform(.delete, path, query: [], body: nil)
    }

    /// Builds the request without sending it. Exposed for tests.
    func request(_ method: HTTPMethod, _ path: String, query: [URLQueryItem] = [], body: Data? = nil, token: String) -> URLRequest {
        var url = apiURL.appending(path: path)
        if !query.isEmpty, var components = URLComponents(url: url, resolvingAgainstBaseURL: false) {
            components.queryItems = query
            url = components.url ?? url
        }
        var request = URLRequest(url: url)
        request.httpMethod = method.rawValue
        request.setValue("Token \(token)", forHTTPHeaderField: "Authorization")
        request.setValue("application/json", forHTTPHeaderField: "Accept")
        if let body {
            request.httpBody = body
            request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        }
        return request
    }

    private func perform(_ method: HTTPMethod, _ path: String, query: [URLQueryItem], body: Data?) async throws -> Data {
        guard let token = await token(), !token.isEmpty else { throw JukeAPIError.notSignedIn }
        let request = request(method, path, query: query, body: body, token: token)
        let data: Data
        let response: URLResponse
        do {
            (data, response) = try await session.data(for: request)
        } catch is CancellationError {
            throw CancellationError()
        } catch let error as URLError where error.code == .cancelled {
            throw CancellationError()
        } catch {
            throw JukeAPIError.transport(error.localizedDescription)
        }
        guard data.count <= maxResponseBytes else { throw JukeAPIError.responseTooLarge }
        guard let http = response as? HTTPURLResponse else { throw JukeAPIError.transport("No HTTP response") }
        guard (200..<300).contains(http.statusCode) else { throw JukeAPIError.from(status: http.statusCode, body: data) }
        return data
    }

    private func decode<Response: Decodable>(_ type: Response.Type, from data: Data) throws -> Response {
        do { return try Self.decoder.decode(Response.self, from: data) }
        catch { throw JukeAPIError.decoding(String(describing: error)) }
    }

    // MARK: Coding

    static let encoder: JSONEncoder = {
        let encoder = JSONEncoder()
        encoder.dateEncodingStrategy = .iso8601
        encoder.outputFormatting = [.sortedKeys]
        return encoder
    }()

    static let decoder: JSONDecoder = {
        let decoder = JSONDecoder()
        decoder.dateDecodingStrategy = .custom { decoder in
            let container = try decoder.singleValueContainer()
            let text = try container.decode(String.self)
            if let date = parseISO8601(text) { return date }
            throw DecodingError.dataCorruptedError(in: container, debugDescription: "Expected an ISO 8601 date, got \(text)")
        }
        return decoder
    }()

    static func parseISO8601(_ text: String) -> Date? {
        if let date = try? Date(text, strategy: .iso8601) { return date }
        let fractional = Date.ISO8601FormatStyle(includingFractionalSeconds: true)
        return try? fractional.parse(text)
    }
}

/// Thread-safe holder for the signed-in user's token, read by `JukeAPI` from
/// any isolation domain. `AppModel` keeps it in step with its session.
final class AccessTokenStore: Sendable {
    private let value = Mutex<String?>(nil)

    func get() -> String? { value.withLock { $0 } }
    func set(_ token: String?) { value.withLock { $0 = token } }
}

import Foundation

enum APIError: LocalizedError {
    case invalidURL
    case httpError(statusCode: Int, message: String?)
    case decodingError(Error)
    case networkError(Error)
    case unauthorized

    var errorDescription: String? {
        switch self {
        case .invalidURL:
            return "Invalid URL"
        case .httpError(let code, let message):
            if let message { return message }
            switch code {
            case 404: return "Resource not found."
            case 403: return "Access denied."
            case 500: return "Server error. Please try again later."
            default: return "Request failed (\(code))."
            }
        case .decodingError(let error):
            return "Failed to parse response: \(error.localizedDescription)"
        case .networkError(let error):
            return error.localizedDescription
        case .unauthorized:
            return "Session expired. Please log in again."
        }
    }
}

final class APIClient {
    static let shared = APIClient()

    let baseURL: String

    private let session: URLSession
    private let decoder: JSONDecoder

    init(baseURL: String? = nil, session: URLSession = .shared) {
        self.baseURL = baseURL ?? APIClient.resolveBaseURL()
        self.session = session

        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        let isoFormatter = ISO8601DateFormatter()
        isoFormatter.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
        let isoFallback = ISO8601DateFormatter()
        isoFallback.formatOptions = [.withInternetDateTime]
        decoder.dateDecodingStrategy = .custom { decoder in
            let container = try decoder.singleValueContainer()
            let str = try container.decode(String.self)
            if let date = isoFormatter.date(from: str) { return date }
            if let date = isoFallback.date(from: str) { return date }
            throw DecodingError.dataCorruptedError(in: container, debugDescription: "Invalid date: \(str)")
        }
        self.decoder = decoder
    }

    private static func resolveBaseURL() -> String {
        let plistURL = Bundle.main.object(forInfoDictionaryKey: "BACKEND_URL") as? String
        return resolveBaseURL(environment: ProcessInfo.processInfo.environment, plistURL: plistURL)
    }

    static func resolveBaseURL(environment: [String: String], plistURL: String?) -> String {
        if let envURL = environment["BACKEND_URL"], !envURL.isEmpty {
            return envURL
        }
        if let plistURL, !plistURL.isEmpty {
            return plistURL
        }
        fatalError("BACKEND_URL must be set in the environment or Info.plist.")
    }

    // MARK: - Request Methods

    func get<T: Decodable>(_ path: String, token: String? = nil, queryItems: [URLQueryItem]? = nil) async throws -> T {
        let request = try buildRequest(method: "GET", path: path, token: token, queryItems: queryItems)
        return try await execute(request)
    }

    func post<T: Decodable>(_ path: String, body: Encodable? = nil, token: String? = nil) async throws -> T {
        let request = try buildRequest(method: "POST", path: path, token: token, body: body)
        return try await execute(request)
    }

    func patch<T: Decodable>(_ path: String, body: Encodable? = nil, token: String? = nil) async throws -> T {
        let request = try buildRequest(method: "PATCH", path: path, token: token, body: body)
        return try await execute(request)
    }

    func delete(_ path: String, token: String? = nil) async throws {
        let request = try buildRequest(method: "DELETE", path: path, token: token)
        let (_, response) = try await session.data(for: request)
        guard let httpResponse = response as? HTTPURLResponse else { return }
        if httpResponse.statusCode == 401 { throw APIError.unauthorized }
        guard (200..<300).contains(httpResponse.statusCode) else {
            throw APIError.httpError(statusCode: httpResponse.statusCode, message: nil)
        }
    }

    func postNoResponse(_ path: String, body: Encodable? = nil, token: String? = nil) async throws {
        let request = try buildRequest(method: "POST", path: path, token: token, body: body)
        let (data, response) = try await session.data(for: request)
        guard let httpResponse = response as? HTTPURLResponse else { return }
        if httpResponse.statusCode == 401 { throw APIError.unauthorized }
        guard (200..<300).contains(httpResponse.statusCode) else {
            let message = extractErrorMessage(from: data)
            throw APIError.httpError(statusCode: httpResponse.statusCode, message: message)
        }
    }

    // MARK: - Internals

    private func buildRequest(method: String, path: String, token: String?, queryItems: [URLQueryItem]? = nil, body: Encodable? = nil) throws -> URLRequest {
        let urlString = baseURL + "/api/v1" + path
        guard var components = URLComponents(string: urlString) else {
            throw APIError.invalidURL
        }
        if let queryItems, !queryItems.isEmpty {
            components.queryItems = queryItems
        }
        guard let url = components.url else {
            throw APIError.invalidURL
        }

        var request = URLRequest(url: url)
        request.httpMethod = method
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.setValue("application/json", forHTTPHeaderField: "Accept")
        request.timeoutInterval = 30

        if let token {
            request.setValue("Token \(token)", forHTTPHeaderField: "Authorization")
        }

        if let body {
            let encoder = JSONEncoder()
            encoder.keyEncodingStrategy = .convertToSnakeCase
            request.httpBody = try encoder.encode(AnyEncodable(body))
        }

        return request
    }

    private func execute<T: Decodable>(_ request: URLRequest) async throws -> T {
        let data: Data
        let response: URLResponse
        do {
            (data, response) = try await session.data(for: request)
        } catch {
            throw APIError.networkError(error)
        }

        guard let httpResponse = response as? HTTPURLResponse else {
            throw APIError.networkError(URLError(.badServerResponse))
        }

        if httpResponse.statusCode == 401 {
            throw APIError.unauthorized
        }

        guard (200..<300).contains(httpResponse.statusCode) else {
            let message = extractErrorMessage(from: data)
            throw APIError.httpError(statusCode: httpResponse.statusCode, message: message)
        }

        do {
            return try decoder.decode(T.self, from: data)
        } catch {
            throw APIError.decodingError(error)
        }
    }

    private func extractErrorMessage(from data: Data) -> String? {
        if let dict = try? JSONSerialization.jsonObject(with: data) as? [String: Any] {
            if let detail = dict["detail"] as? String { return detail }
            if let nonField = dict["non_field_errors"] as? [String] { return nonField.joined(separator: " ") }
            if let firstValue = dict.values.first as? [String] { return firstValue.first }
        }
        // Don't return raw HTML or other non-JSON responses as error messages
        return nil
    }
}

// MARK: - AnyEncodable

private struct AnyEncodable: Encodable {
    let value: Encodable

    init(_ value: Encodable) {
        self.value = value
    }

    func encode(to encoder: Encoder) throws {
        try value.encode(to: encoder)
    }
}

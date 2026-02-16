import Foundation

/// Utilities for parsing ISO8601 dates from the Juke API.
///
/// The API may return dates in various ISO8601 formats:
/// - With fractional seconds: `2026-01-15T10:30:00.123Z`
/// - Without fractional seconds: `2026-01-15T10:30:00Z`
/// - With microseconds: `2026-01-15T10:30:00.123456Z`
/// - With timezone offset: `2026-01-15T10:30:00.123456+00:00`
public enum JukeDateParsing {

    // MARK: - Formatters

    private static let iso8601WithFractionalSeconds: ISO8601DateFormatter = {
        let formatter = ISO8601DateFormatter()
        formatter.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
        return formatter
    }()

    private static let iso8601WithoutFractionalSeconds: ISO8601DateFormatter = {
        let formatter = ISO8601DateFormatter()
        formatter.formatOptions = [.withInternetDateTime]
        return formatter
    }()

    private static let iso8601Microseconds: DateFormatter = {
        let formatter = DateFormatter()
        formatter.calendar = Calendar(identifier: .iso8601)
        formatter.locale = Locale(identifier: "en_US_POSIX")
        formatter.timeZone = TimeZone(secondsFromGMT: 0)
        formatter.dateFormat = "yyyy-MM-dd'T'HH:mm:ss.SSSSSSZ"
        return formatter
    }()

    private static let iso8601MicrosecondsWithTimezone: DateFormatter = {
        let formatter = DateFormatter()
        formatter.calendar = Calendar(identifier: .iso8601)
        formatter.locale = Locale(identifier: "en_US_POSIX")
        formatter.timeZone = TimeZone(secondsFromGMT: 0)
        formatter.dateFormat = "yyyy-MM-dd'T'HH:mm:ss.SSSSSSXXXXX"
        return formatter
    }()

    // MARK: - Public API

    /// Parses an ISO8601 date string, trying multiple formats.
    /// - Parameter string: The date string to parse.
    /// - Returns: The parsed date, or nil if parsing fails.
    public static func parse(_ string: String) -> Date? {
        if let date = iso8601WithFractionalSeconds.date(from: string) {
            return date
        }
        if let date = iso8601WithoutFractionalSeconds.date(from: string) {
            return date
        }
        if let date = iso8601Microseconds.date(from: string) {
            return date
        }
        if let date = iso8601MicrosecondsWithTimezone.date(from: string) {
            return date
        }
        return nil
    }

    /// A JSONDecoder configured for Juke API responses.
    ///
    /// Uses custom date decoding that tries multiple ISO8601 formats.
    public static func makeDecoder() -> JSONDecoder {
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        decoder.dateDecodingStrategy = .custom { decoder in
            let container = try decoder.singleValueContainer()
            let value = try container.decode(String.self)
            if let date = parse(value) {
                return date
            }
            throw DecodingError.dataCorruptedError(
                in: container,
                debugDescription: "Invalid ISO8601 date: \(value)"
            )
        }
        return decoder
    }
}

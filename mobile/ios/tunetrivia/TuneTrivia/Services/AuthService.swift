//
//  AuthService.swift
//  TuneTrivia
//
//  Created by Juke Platform on 2026-01-22.
//

import Foundation

struct AuthTokenResponse: Decodable {
    let token: String
}

struct RegisterResponse: Decodable {
    let detail: String?
}

struct LoginRequest: Encodable {
    let username: String
    let password: String
}

struct RegisterRequest: Encodable {
    let username: String
    let email: String
    let password: String
    let passwordConfirm: String

    enum CodingKeys: String, CodingKey {
        case username
        case email
        case password
        case passwordConfirm = "password_confirm"
    }
}

final class AuthService {
    private let client: APIClient
    private let encoder: JSONEncoder

    init(client: APIClient = .shared) {
        self.client = client
        self.encoder = JSONEncoder()
        self.encoder.keyEncodingStrategy = .convertToSnakeCase
    }

    func login(username: String, password: String) async throws -> String {
        let payload = LoginRequest(username: username, password: password)
        let body = try encoder.encode(payload)
        let response: AuthTokenResponse = try await client.send(
            "/api/v1/auth/api-auth-token/",
            method: .post,
            body: body
        )
        return response.token
    }

    func register(username: String, email: String, password: String, passwordConfirm: String) async throws -> RegisterResponse {
        let payload = RegisterRequest(username: username, email: email, password: password, passwordConfirm: passwordConfirm)
        let body = try encoder.encode(payload)
        return try await client.send(
            "/api/v1/auth/accounts/register/",
            method: .post,
            body: body
        )
    }
}

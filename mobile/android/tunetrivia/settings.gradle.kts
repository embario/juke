pluginManagement {
    repositories {
        google()
        mavenCentral()
        gradlePluginPortal()
    }
}

dependencyResolutionManagement {
    repositoriesMode.set(RepositoriesMode.FAIL_ON_PROJECT_REPOS)
    repositories {
        google()
        mavenCentral()
    }
}

rootProject.name = "TuneTrivia"
include(":app")

includeBuild("../../Packages/JukeCore") {
    dependencySubstitution {
        substitute(module("fm.juke:core")).using(project(":"))
    }
}

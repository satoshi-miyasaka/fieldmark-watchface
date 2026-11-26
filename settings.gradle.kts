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

rootProject.name = "fieldmark-watchface"
// watchface: the FIELDMARK watch face (Watch Face Format, no code).
// wear: the companion app on the watch that reads wind, sun and tide from Open-Meteo.
include(":watchface", ":wear")

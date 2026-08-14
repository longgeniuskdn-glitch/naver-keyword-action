plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
}

android {
    namespace = "com.myvision.naverclipautoswipe"
    compileSdk = 34

    defaultConfig {
        applicationId = "com.myvision.naverclipautoswipe"
        minSdk = 30
        targetSdk = 30
        versionCode = 8
        versionName = "0.3.2"
    }

    buildTypes {
        release { isMinifyEnabled = false }
    }

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_1_8
        targetCompatibility = JavaVersion.VERSION_1_8
    }
    kotlinOptions { jvmTarget = "1.8" }
}

dependencies {
    implementation("androidx.core:core-ktx:1.12.0")
    implementation("org.jetbrains.kotlinx:kotlinx-coroutines-android:1.7.3")
    implementation("com.github.MuntashirAkon:libadb-android:3.1.0")
    implementation("org.conscrypt:conscrypt-android:2.5.3")
    implementation("com.github.MuntashirAkon:sun-security-android:1.1")
}

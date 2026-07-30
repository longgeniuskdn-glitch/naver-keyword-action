plugins { id("com.android.application") }

android {
    namespace = "com.myvision.codexusage"
    compileSdk = 35

    defaultConfig {
        applicationId = "com.myvision.codexusage"
        minSdk = 26
        targetSdk = 35
        versionCode = 20
        versionName = "0.2.0"
    }

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }
}

dependencies {
    implementation("androidx.browser:browser:1.8.0")
    implementation("androidx.core:core:1.15.0")
}

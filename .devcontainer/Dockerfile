FROM mcr.microsoft.com/devcontainers/base:ubuntu-24.04

ENV DEBIAN_FRONTEND=noninteractive

# ---------------------------------------------------------------------------
# Python 3.11+ (Ubuntu 24.04 يوفر 3.12 افتراضيًا)، أدوات نظام أساسية،
# عميل PostgreSQL (خادم قاعدة البيانات نفسه في حاوية db منفصلة عبر docker-compose)
# ---------------------------------------------------------------------------
RUN apt-get update && apt-get install -y --no-install-recommends \
        python3 python3-pip python3-venv \
        postgresql-client \
        unzip wget curl git \
        openjdk-17-jdk-headless \
    && rm -rf /var/lib/apt/lists/*

ENV JAVA_HOME=/usr/lib/jvm/java-17-openjdk-amd64
ENV PATH="${JAVA_HOME}/bin:${PATH}"

# ---------------------------------------------------------------------------
# Gradle (مُثبَّت في النظام لأن مشروع android/ الحالي لا يتضمن Gradle Wrapper)
# ---------------------------------------------------------------------------
ENV GRADLE_VERSION=8.7
RUN wget -q "https://services.gradle.org/distributions/gradle-${GRADLE_VERSION}-bin.zip" -O /tmp/gradle.zip \
    && unzip -q /tmp/gradle.zip -d /opt \
    && rm /tmp/gradle.zip
ENV PATH="/opt/gradle-${GRADLE_VERSION}/bin:${PATH}"

# ---------------------------------------------------------------------------
# Android SDK command-line tools + platform-tools (adb) + build-tools + platform 34
# ---------------------------------------------------------------------------
ENV ANDROID_HOME=/opt/android-sdk
RUN mkdir -p "${ANDROID_HOME}/cmdline-tools" \
    && wget -q "https://dl.google.com/android/repository/commandlinetools-linux-11076708_latest.zip" -O /tmp/cmdline-tools.zip \
    && unzip -q /tmp/cmdline-tools.zip -d "${ANDROID_HOME}/cmdline-tools" \
    && mv "${ANDROID_HOME}/cmdline-tools/cmdline-tools" "${ANDROID_HOME}/cmdline-tools/latest" \
    && rm /tmp/cmdline-tools.zip

ENV PATH="${ANDROID_HOME}/cmdline-tools/latest/bin:${ANDROID_HOME}/platform-tools:${PATH}"

RUN yes | sdkmanager --licenses > /dev/null 2>&1 || true \
    && sdkmanager --install "platform-tools" "platforms;android-34" "build-tools;34.0.0" > /dev/null

WORKDIR /workspace

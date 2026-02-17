# Use an official Python runtime as a parent image
# python:3.9-slim is a good balance of size and compatibility found on both x86 and ARM (Raspberry Pi)
# Using Python 3.12-slim to support pandas-ta >= 3.12 requirement
FROM python:3.12-slim
# Set the working directory in the container
WORKDIR /app

# Install system dependencies
# build-essential and libffi-dev are often required for building Python packages like pandas, numpy, or cryptography on ARM
# Install TA-Lib C-library (pre-compiled version from Debian repositories)
# On Debian/Ubuntu, the package name is often libta-lib0-dev or ta-lib
# We add it to the system dependencies list.
RUN apt-get update && apt-get install -y \
    build-essential \
    libffi-dev \
    gcc \
    git \
    wget \
    tar \
    && rm -rf /var/lib/apt/lists/*

# Install TA-Lib C-library (required for some technical analysis libraries)
# We use the GitHub release as it is more reliable than SourceForge
# RUN wget https://github.com/TA-Lib/ta-lib/releases/download/v0.4.0/ta-lib-0.4.0-src.tar.gz && \
#     tar -xvzf ta-lib-0.4.0-src.tar.gz && \
#     cd ta-lib/ && \
#     ./configure --prefix=/usr && \
#     make && \
#     make install && \
#     cd .. && \
#     rm -rf ta-lib ta-lib-0.4.0-src.tar.gz

# Copy the requirements file into the container at /app
# Copy the requirements file and local wheel into the container
COPY requirements.txt .
# COPY pandas_ta-0.4.71b0-py3-none-any.whl .

# Install any needed packages specified in requirements.txt
# We upgrade pip first to ensure we have the latest features/fixes
RUN pip install --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Copy the rest of the application code
COPY . .

# backend/data is where cached data lives, ensure it exists
RUN mkdir -p backend/data

# Make port 5000 available to the world outside this container
EXPOSE 5000

# Define environment variable for Flask
ENV FLASK_APP=run.py
ENV FLASK_ENV=production

# Run app.py when the container launches
CMD ["python", "run.py"]

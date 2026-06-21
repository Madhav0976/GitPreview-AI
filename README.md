# 🚀 GitPreview AI

<div align="center">

### Instantly Understand Any GitHub Repository with AI-Powered Insights

Analyze repository structure, detect technologies, discover entry points, and generate intelligent repository summaries in seconds.

<br/>

![Next.js](https://img.shields.io/badge/Next.js-15+-black?style=for-the-badge\&logo=next.js)
![React](https://img.shields.io/badge/React-19-blue?style=for-the-badge\&logo=react)
![TypeScript](https://img.shields.io/badge/TypeScript-5+-3178C6?style=for-the-badge\&logo=typescript)
![FastAPI](https://img.shields.io/badge/FastAPI-Latest-009688?style=for-the-badge\&logo=fastapi)
![Python](https://img.shields.io/badge/Python-3.11+-3776AB?style=for-the-badge\&logo=python)
![GitHub\_API](https://img.shields.io/badge/GitHub-REST_API-181717?style=for-the-badge\&logo=github)

![License](https://img.shields.io/badge/License-MIT-green?style=flat-square)
![PRs Welcome](https://img.shields.io/badge/PRs-Welcome-brightgreen.svg?style=flat-square)
![Open Source](https://img.shields.io/badge/Open%20Source-Love-red?style=flat-square)
![Maintained](https://img.shields.io/badge/Maintained-Yes-success?style=flat-square)

</div>

---

## 📖 Project Description

**GitPreview AI** is an intelligent repository analysis platform that helps developers quickly understand unfamiliar GitHub repositories.

Instead of manually browsing folders, source files, and configuration files, GitPreview AI automatically analyzes repository metadata, technology stacks, project structure, entry points, important files, and generates AI-style summaries and insights.

Whether you're evaluating open-source projects, onboarding to a new codebase, conducting technical due diligence, or exploring repositories, GitPreview AI provides a clear and structured overview within seconds.

---

## ✨ Features

### 🔍 Repository Analysis

* Analyze any public GitHub repository using its URL
* Repository metadata extraction
* Repository validation and accessibility checks

### 🧠 Smart Technology Detection

* Framework detection
* Library identification
* Technology stack analysis
* Package manager detection

### 📂 Structure Intelligence

* Folder structure analysis
* Important file discovery
* Repository organization insights
* Architecture overview generation

### 🚪 Entry Point Discovery

* Detect application entry points
* Identify startup files
* Framework-specific bootstrapping analysis

### 📊 Repository Insights

* Language distribution visualization
* Development stack overview
* Repository health indicators
* Project type classification

### 🤖 AI-Powered Summary

* Human-readable repository explanations
* Key functionality summaries
* Architecture insights
* Project purpose detection

### 🎨 Modern User Experience

* Responsive design
* Clean dashboard interface
* Fast analysis workflow
* Developer-friendly visualization

---

# 📸 Screenshots

### Dashboard                                                                                                   
                                                                             
<img width="1916" height="992" alt="image" src="https://github.com/user-attachments/assets/b87fc985-6582-4430-a906-9e2c53166e46" /> 


### Repository Analysis    

<img width="1142" height="426" alt="image" src="https://github.com/user-attachments/assets/7dd2583f-efa1-4872-af9f-35c47d3f47be" />


### Insights View                  

<img width="1111" height="159" alt="image" src="https://github.com/user-attachments/assets/fecf51a1-f42b-4101-9401-c75f66df4157" />


### Language Distribution  

<img width="1085" height="805" alt="image" src="https://github.com/user-attachments/assets/d19f5fb6-5ee2-46b0-aa63-5fe89abb1b52" />


---

# 🏗️ Architecture Overview

```text
┌─────────────────────────────┐
│          User               │
└─────────────┬───────────────┘
              │
              ▼
┌─────────────────────────────┐
│      Next.js Frontend       │
│    React + TypeScript UI    │
└─────────────┬───────────────┘
              │ REST API
              ▼
┌─────────────────────────────┐
│      FastAPI Backend        │
│ Repository Analysis Engine  │
└─────────────┬───────────────┘
              │
              ▼
┌─────────────────────────────┐
│      GitHub REST API        │
└─────────────┬───────────────┘
              │
              ▼
┌─────────────────────────────┐
│ Metadata & Repository Data  │
└─────────────────────────────┘
```

---

# ⚙️ Tech Stack

## Frontend

| Technology   | Purpose               |
| ------------ | --------------------- |
| Next.js      | Frontend Framework    |
| React        | UI Development        |
| TypeScript   | Type Safety           |
| Tailwind CSS | Styling               |
| Fetch API    | Backend Communication |

## Backend

| Technology | Purpose               |
| ---------- | --------------------- |
| FastAPI    | API Framework         |
| Python     | Core Backend Language |
| HTTPX      | GitHub API Requests   |
| Pydantic   | Data Validation       |

## External Services

| Service         | Purpose                                  |
| --------------- | ---------------------------------------- |
| GitHub REST API | Repository Metadata & Structure Analysis |

---

# 🚀 Installation Guide

## Prerequisites

Ensure the following tools are installed:

| Requirement | Version |
| ----------- | ------- |
| Node.js     | 18+     |
| npm / pnpm  | Latest  |
| Python      | 3.11+   |
| Git         | Latest  |

---

# 🔧 Backend Setup

### 1. Clone Repository

```bash
git clone https://github.com/your-username/gitpreview-ai.git

cd gitpreview-ai
```

### 2. Navigate to Backend

```bash
cd backend
```

### 3. Create Virtual Environment

```bash
python -m venv venv
```

### 4. Activate Environment

#### Windows

```bash
venv\Scripts\activate
```

#### macOS/Linux

```bash
source venv/bin/activate
```

### 5. Install Dependencies

```bash
pip install -r requirements.txt
```

### 6. Configure Environment Variables

```bash
cp .env.example .env
```

### 7. Run Backend

```bash
uvicorn app.main:app --reload
```

Backend will start at:

```text
http://localhost:8000
```

---

# 💻 Frontend Setup

### 1. Navigate to Frontend

```bash
cd frontend
```

### 2. Install Dependencies

```bash
npm install
```

or

```bash
pnpm install
```

### 3. Configure Environment Variables

```bash
cp .env.example .env.local
```

### 4. Start Development Server

```bash
npm run dev
```

Application will run at:

```text
http://localhost:3000
```

---

# 🔐 Environment Variables

## Backend

Create:

```bash
backend/.env
```

```env
GITHUB_TOKEN=your_github_personal_access_token
```

## Frontend

Create:

```bash
frontend/.env.local
```

```env
NEXT_PUBLIC_API_URL=http://localhost:8000
```

---

# 📚 Usage

### Step 1

Open the application.

### Step 2

Paste a GitHub repository URL.

Example:

```text
https://github.com/vercel/next.js
```

### Step 3

Click **Analyze Repository**.

### Step 4

GitPreview AI will:

* Validate repository
* Fetch metadata
* Detect technologies
* Analyze structure
* Discover entry points
* Generate repository insights
* Create AI-powered summaries

### Step 5

Review results inside the analysis dashboard.

---

# 📁 Folder Structure

```text
gitpreview-ai/
│
├── backend/
│   ├── app/
│   │   ├── api/
│   │   ├── services/
│   │   ├── analyzers/
│   │   ├── models/
│   │   ├── schemas/
│   │   └── main.py
│   │
│   ├── requirements.txt
│   └── .env
│
├── frontend/
│   ├── src/
│   │   ├── app/
│   │   ├── components/
│   │   ├── hooks/
│   │   ├── services/
│   │   ├── types/
│   │   └── utils/
│   │
│   ├── public/
│   ├── package.json
│   └── .env.local
│
├── docs/
│   └── screenshots/
│
├── README.md
└── LICENSE
```

---

# 🔌 API Endpoints

## Base URL

```text
http://localhost:8000
```

### Analyze Repository

```http
POST /api/analyze
```

#### Request

```json
{
  "repository_url": "https://github.com/vercel/next.js"
}
```

#### Response

```json
{
  "repository_name": "next.js",
  "owner": "vercel",
  "description": "The React Framework",
  "technologies": [
    "Next.js",
    "React",
    "TypeScript"
  ],
  "entry_points": [
    "src/index.ts"
  ],
  "important_files": [
    "package.json",
    "README.md"
  ],
  "summary": "AI-generated repository summary..."
}
```

---

# 🔮 Future Enhancements

* [ ] GitHub Repository Comparison
* [ ] Repository Health Score
* [ ] Security Analysis
* [ ] Dependency Visualization
* [ ] Architecture Diagram Generation
* [ ] OpenAI-Powered Deep Summaries
* [ ] Repository Chat Assistant
* [ ] Export Analysis as PDF
* [ ] Team Collaboration Features
* [ ] Repository Trend Insights
* [ ] Multi-Repository Analysis
* [ ] GitHub App Integration

---

# 🤝 Contributing

Contributions are welcome and greatly appreciated.

### Development Workflow

1. Fork the repository
2. Create a feature branch

```bash
git checkout -b feature/amazing-feature
```

3. Commit your changes

```bash
git commit -m "Add amazing feature"
```

4. Push to your branch

```bash
git push origin feature/amazing-feature
```

5. Open a Pull Request

---

<details>
<summary><strong>📋 Contribution Guidelines</strong></summary>

### Before Submitting

* Follow coding standards
* Add appropriate tests
* Update documentation
* Ensure linting passes
* Keep pull requests focused and concise

### Code Quality

```bash
# Frontend
npm run lint

# Backend
pytest
```

</details>

---

## 👨‍💻 Author

**T. V. Bindu Madhav** *Computer Science & Engineering Student | Full Stack Developer | AI/ML Enthusiast*

* **GitHub:** [@Madhav0976](https://github.com/Madhav0976)
* **LinkedIn:** [in/madhavtanguturi](https://www.linkedin.com/in/madhavtanguturi)

---

<div align="center">

### ⭐ If you find GitPreview AI useful, consider giving it a star!

Built with ❤️ using Next.js, FastAPI, and the GitHub API.

</div>

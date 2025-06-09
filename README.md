# 🔍 Username Matching System

This project is a **Flask web application** that takes a username input and predicts the most likely employee(s) it belongs to using intelligent fuzzy matching and phonetic similarity.

---

## 🚀 Features

- Match usernames against employee data using:
  - **Fuzzy string matching** (`thefuzz`)
  - **Phonetic algorithms** (`jellyfish` - Soundex, Metaphone)
  - **Heuristics** (e.g., employee ID presence in username)
- Ranks and returns:
  - **Best matches** (confidence score ≥ 65)
  - **Top suggestions** if no strong match is found
- Clean web UI for input and result display

---

## 🧠 Tech Stack

| Component     | Technology        |
|---------------|-------------------|
| Backend       | Python 3, Flask   |
| Matching Algo | thefuzz, jellyfish|
| Frontend      | HTML (via Jinja)  |
| Data Handling | pandas            |

---

## 📊 Employee CSV Format

Your `employee_data.csv` should include the following columns:

| emp_id | first_name | last_name |
|--------|------------|-----------|
| 101    | Alice      | Johnson   |
| 102    | Bob        | Smith     |

---

## 🛠️ Setup & Installation

1. **Clone the repository**
```bash
git clone https://github.com/your-username/username-matching-app.git
cd username-matching-app
```
## Create Virtual Environment
```
python -m venv venv
source venv/bin/activate   # On Windows: venv\Scripts\activate
```
## Install Dependencies
```
pip install -r requirements.txt
```
## Run the app

```
python app.py
```

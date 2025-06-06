from flask import Flask, render_template, request
import pandas as pd
from thefuzz import fuzz
import jellyfish
import joblib


app = Flask(__name__)
model = joblib.load('/Users/midhun/Developer/Git/Name_match_ml/TRAINED_MODELS/model(Accu~90).pkl')


def compute_features(username, employee_name):
    return [
        fuzz.ratio(username, employee_name),
        fuzz.partial_ratio(username, employee_name),
        fuzz.token_set_ratio(username, employee_name),
        int(jellyfish.soundex(username) == jellyfish.soundex(employee_name)),
        int(jellyfish.metaphone(username) == jellyfish.metaphone(employee_name))
    ]

def fetch_employees():
    try:
        df = pd.read_csv('employee_data.csv')
        df.columns = df.columns.str.lower()
        required_columns = {'emp_id', 'first_name', 'last_name'}
        if not required_columns.issubset(df.columns):
            return pd.DataFrame(columns=['emp_id', 'employee_name'])
        df['employee_name'] = df['first_name'].str.strip() + ' ' + df['last_name'].str.strip()
        return df[['emp_id', 'employee_name']]
    except:
        return pd.DataFrame(columns=['emp_id', 'employee_name'])


@app.route('/', methods=['GET', 'POST'])
def index():
    matches = []
    top_matches = []
    input_username = ""
    if request.method == 'POST':
        input_username = request.form['username'].strip()
        employees = fetch_employees()
        if not employees.empty:
            features = employees['employee_name'].apply(lambda en: compute_features(input_username, en))
            features_df = pd.DataFrame(list(features), columns=[
                'levenshtein', 'partial_ratio', 'token_set_ratio', 'soundex_match', 'metaphone_match'
            ])
            probs = model.predict_proba(features_df)[:, 1]
            employees['probability'] = probs

            matches = employees[employees['probability'] >= 0.8].sort_values('probability', ascending=False).to_dict(orient='records')
            top_matches = employees.sort_values('probability', ascending=False).head(5).to_dict(orient='records')

    return render_template('index.html', matches=matches, top_matches=top_matches, input_username=input_username)

if __name__ == '__main__':
    app.run(debug=True)
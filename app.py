from flask import Flask, render_template, request, jsonify
import json
import os
import logging
from langchain.prompts import PromptTemplate
from langchain.chains import LLMChain, SequentialChain
from langchain.callbacks import get_openai_callback
from langchain.chat_models import ChatOpenAI
import requests
from io import BytesIO
import PyPDF2
import fitz
import tempfile


app = Flask(__name__)

# Set up logging
logging.basicConfig(filename='app.log', level=logging.INFO)

TEMPLATE = """
Text:{text}
You are an expert MCQ maker. Given the above text, it is your job to \
create a quiz of {number} multiple choice questions for {subject} students in {tone} tone. 
Make sure the questions are not repeated and check all the questions to be conforming the text as well.
Make sure to format your response like RESPONSE_JSON below and use it as a guide. \
Ensure to make {number} MCQs
### RESPONSE_JSON
{response_json}
"""

TEMPLATE2 = """
You are an expert English grammarian and writer. Given a Multiple Choice Quiz for {subject} students.\
You need to evaluate the complexity of the question and give a complete analysis of the quiz. Only use at max 50 words for complexity analysis. 
if the quiz is not at par with the cognitive and analytical abilities of the students,\
update the quiz questions which need to be changed and change the tone such that it perfectly fits the student abilities
Quiz_MCQs:
{quiz}

Check from an expert English Writer of the above quiz:
"""

quiz_file = 'quiz.json'

def download_pdf(pdf_url):
    response = requests.get(pdf_url)
    return BytesIO(response.content)
            
def pdf_to_text(pdf_bytes):
    pdf_reader = PyPDF2.PdfReader(pdf_bytes)
    text = ""

    for page_num in range(len(pdf_reader.pages)):
        page = pdf_reader.pages[page_num]
        text += page.extract_text()

    return text



@app.route('/')
def home():
    return render_template("index.html")

@app.route('/quiz', methods=['GET', 'POST'])
def quiz():
    try:
        if request.method == 'POST':
            api_key = request.form['apiKey']
            SUBJECT = request.form['subject']
            TONE = request.form['ton']
            NUMBER = int(request.form['numQuestions'])
            document_link = request.form['documentLink']
            file_upload = request.files['fileUpload']

                    
            if file_upload:
    # Check if the uploaded file is a PDF
                  if file_upload.filename.endswith('.pdf'):
                       pdf_content = pdf_to_text(file_upload.stream)
                  else:
        # Read content from the uploaded text file
                    file_upload.save(os.path.join('uploads', file_upload.filename))
                    file_path = os.path.join('uploads', file_upload.filename)
                    with open(file_path, 'r', encoding='utf-8', errors='ignore') as file:
                      pdf_content = file.read()

            elif document_link:
    # Check if the document link points to a PDF
                 if document_link.endswith('.pdf'):
                      pdf_bytes = download_pdf(document_link)
                      pdf_content = pdf_to_text(pdf_bytes)
                 else:
        # Fetch content from the document link
                       document_response = requests.get(document_link)
                       pdf_content = document_response.text
            
            with open('Response.json') as json_file:
              RESPONSE_JSON_STRING = json_file.read()

             # Ensure that RESPONSE_JSON_STRING is correctly loaded
            print("RESPONSE_JSON_STRING:", RESPONSE_JSON_STRING)

            RESPONSE_JSON = json.loads(RESPONSE_JSON_STRING)

             # Ensure that RESPONSE_JSON is correctly parsed
            print("RESPONSE_JSON:", RESPONSE_JSON) 


            llm = ChatOpenAI(openai_api_key=api_key, model="gpt-3.5-turbo", temperature=0.5)

            quiz_generation_prompt = PromptTemplate(
                input_variables=["text", "number", "subject", "tone", "response_json"],
                template=TEMPLATE
            )
            quiz_chain = LLMChain(llm=llm, prompt=quiz_generation_prompt, output_key="quiz", verbose=True)
            quiz_evaluation_prompt = PromptTemplate(input_variables=["subject", "quiz"], template=TEMPLATE)

            review_chain = LLMChain(llm=llm, prompt=quiz_evaluation_prompt, output_key="review", verbose=True)

            generate_evaluate_chain = SequentialChain(chains=[quiz_chain, review_chain],
                                                      input_variables=["text", "number", "subject", "tone", "response_json"],
                                                      output_variables=["quiz", "review"], verbose=True)

            with get_openai_callback() as cb:
                response = generate_evaluate_chain(
                    {
                        "text": pdf_content,
                        "number": NUMBER,
                        "subject": SUBJECT,
                        "tone": TONE,
                        "response_json": RESPONSE_JSON_STRING
                    }
                )

            quiz = response.get("quiz")
            quiz = json.loads(quiz)

            with open('quiz.json', 'w') as file:
                json.dump(quiz, file)

    except Exception as e:
        logging.error(f"An error occurred: {str(e)}")
        return render_template("error.html", error_message=f"An error occurred: {str(e)}")

    with open('quiz.json') as json_file:
        quiz_data = json.load(json_file)

    return render_template("quiz.html", quiz_data=quiz_data)


# Function to extract text from a PDF file
def extract_text_from_pdf(file_upload):
    text = ""
    with file_upload.stream as pdf_stream:
        pdf_reader = PyPDF2.PdfReader(pdf_stream)
        for page_number in range(len(pdf_reader.pages)):
            page = pdf_reader.pages[page_number]
            text += page.extract_text()
    return text


# Function to extract text from a PDF file given a URL
def extract_text_from_pdf_url(url):
    text = ""
    pdf_bytes = download_pdf(url)
    
    # Use PdfReader instead of PdfFileReader
    pdf_reader = PyPDF2.PdfReader(pdf_bytes)

    # Create a temporary file
    with tempfile.NamedTemporaryFile(delete=False, suffix=".txt", mode="w", encoding='utf-8') as text_file:
        for page_num in range(len(pdf_reader.pages)):
            page = pdf_reader.pages[page_num]
            text_file.write(page.extract_text())
    
    # Read the content from the temporary file
    with open(text_file.name, 'r') as file:
        text = file.read()

    # Remove the temporary file
    os.remove(text_file.name)
    
    return text


@app.route('/result', methods=['GET', 'POST'])
def result():
    try:
        user_responses = {}

        for question_number in request.form:
            user_response = request.form[question_number]
            question_number = question_number.replace('question', '')
            user_responses[question_number] = user_response

        with open('quiz.json') as json_file:
            quiz_data = json.load(json_file)

        return render_template("result.html", user_responses=user_responses, quiz_data=quiz_data)

    except Exception as e:
        logging.error(f"An error occurred: {str(e)}")
        return render_template("error.html", error_message=f"An error occurred: {str(e)}")

if __name__ == '__main__':
    app.run(debug=True)

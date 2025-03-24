import { AIChatResponse, MessageSenders, QuestionTypes } from "@/types";

const aiResponses: AIChatResponse[] = [
  {
    id: 1,
    sender: MessageSenders.AI,
    type: "text",
    content: "Welcome! Today we will learn some Portuguese.",
    payload: { text: "Let’s begin!" }
  },
  {
    id: 2,
    sender: MessageSenders.AI,
    type: "question",
    content: "Here are your first questions:",
    payload: {
      questions: [
        {
          id: "q1",
          type: QuestionTypes.MultipleChoice,
          questionText: "What is the capital of Portugal?",
          questionDescription: "Choose the correct capital city.",
          options: ["Madrid", "Lisbon", "Porto", "Barcelona"],
          correct_answers: ["Lisbon"],
          difficulty: "easy",
          hint: "It starts with L"
        },
        {
          id: "q2",
          type: QuestionTypes.MultipleChoice,
          questionText: "Which of these is a famous Portuguese dish?",
          questionDescription: "Select the correct dish.",
          options: ["Paella", "Sushi", "Bacalhau", "Pizza"],
          correct_answers: ["Bacalhau"],
          difficulty: "medium",
          hint: "It’s made from codfish."
        },
        {
          id: "q3",
          type: QuestionTypes.FillInTheBlanks,
          questionText: "Complete the sentence with the correct word:",
          questionDescription: "Use the correct verb in Portuguese.",
          questionSentence: "Eu ____ português todos os dias.", // "I speak Portuguese every day."
          correct_answers: ["falo"],
          difficulty: "medium",
          hint: 'The verb starts with "f".',
          blankSeparator: "____",
          numberOfBlanks: 1
        },
        {
          id: "q4",
          type: QuestionTypes.FillInTheBlanks,
          questionText: "Translate and complete the sentence:",
          questionDescription: 'The translation of "We live in Portugal" is:',
          questionSentence: "Nós ____ em Portugal.",
          correct_answers: ["moramos"],
          difficulty: "hard",
          hint: 'The verb starts with "m".',
          blankSeparator: "____",
          numberOfBlanks: 1
        },
        {
          id: "q5",
          type: QuestionTypes.FillInTheBlanks,
          questionText: "Complete the sentence with the correct verb and noun:",
          questionDescription: 'Translate the sentence: "They eat fish every day."',
          questionSentence: "Eles ____ peixe todos os dias.",
          correct_answers: ["comem", "peixe"],
          difficulty: "medium",
          hint: 'The verb starts with "c" and the noun is related to food.',
          blankSeparator: "____",
          numberOfBlanks: 2
        },
        {
          id: "q6",
          type: QuestionTypes.FillInTheBlanks,
          questionText: "Complete the sentence with the correct pronoun and verb:",
          questionDescription: 'The translation of "She studies at school" is:',
          questionSentence: "Ela ____ na escola.",
          correct_answers: ["estuda"],
          difficulty: "easy",
          hint: 'The verb starts with "e".',
          blankSeparator: "____",
          numberOfBlanks: 1
        },
        // {
        //   id: "q7",
        //   type: QuestionTypes.FillInTheBlanks,
        //   questionText: "Translate and complete the sentence with the correct words:",
        //   questionDescription: "Fill in the blanks for the sentence: 'I am learning Portuguese at the university.'",
        //   questionSentence: "Eu ____ português na ____.",
        //   correct_answers: ["estou", "universidade"],
        //   difficulty: "hard",
        //   hint: 'The first word is a conjugation of the verb "estar" and the second is related to education.',
        //   blankSeparator: "____",
        //   numberOfBlanks: 2
        // }
      ]
    }
  },
  {
    id: 3,
    sender: MessageSenders.AI,
    type: "correction",
    content: "That is correct! Lisbon is the capital of Portugal.",
    payload: { text: "Great job!" }
  },
  {
    id: 4,
    sender: MessageSenders.AI,
    type: "question",
    content: "Complete the following sentences:",
    payload: {
      questions: [
        {
          id: "q8",
          type: QuestionTypes.FillInTheBlanks,
          questionText: "Complete the sentence with the correct word:",
          questionDescription: "Use the correct verb in Portuguese.",
          questionSentence: "Eu ____ português todos os dias.", // "I speak Portuguese every day."
          correct_answers: ["falo"],
          difficulty: "medium",
          hint: 'The verb starts with "f".',
          blankSeparator: "____",
          numberOfBlanks: 1
        },
        {
          id: "q9",
          type: QuestionTypes.FillInTheBlanks,
          questionText: "Translate and complete the sentence:",
          questionDescription: 'The translation of "We live in Portugal" is:',
          questionSentence: "Nós ____ em Portugal.",
          correct_answers: ["moramos"],
          difficulty: "hard",
          hint: 'The verb starts with "m".',
          blankSeparator: "____",
          numberOfBlanks: 1
        }
      ]
    }
  },
  {
    id: 5,
    sender: MessageSenders.AI,
    type: "hint",
    content: "Hint: The verb starts with 'f'.",
    payload: { text: 'Think about the conjugation of "falar".' }
  },
  {
    id: 6,
    sender: MessageSenders.AI,
    type: "explanation",
    content: "Let me explain:",
    payload: { text: '"Falar" means "to speak". The correct conjugation is "Eu falo".' }
  },
  {
    id: 7,
    sender: MessageSenders.AI,
    type: "feedback",
    content: "You are doing great!",
    payload: { text: "Keep practicing, and you’ll improve quickly!" }
  }
];

export { aiResponses };

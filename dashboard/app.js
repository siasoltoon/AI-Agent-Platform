const API_BASE = "http://127.0.0.1:8000";

const runButton = document.getElementById("runButton");
const promptInput = document.getElementById("prompt");
const modelInput = document.getElementById("model");

const statusElement = document.getElementById("status");
const resultElement = document.getElementById("result");
const taskIdElement = document.getElementById("taskId");


runButton.addEventListener("click", async () => {

    const prompt = promptInput.value.trim();
    const model = modelInput.value.trim();


    if (!prompt) {

        statusElement.textContent =
            "Please enter a task.";

        return;
    }


    runButton.disabled = true;

    statusElement.textContent =
        "Running...";

    resultElement.textContent =
        "Waiting for Agent...";

    taskIdElement.textContent =
        "-";


    try {

        const response = await fetch(
            `${API_BASE}/tasks/create`,
            {
                method: "POST",

                headers: {
                    "Content-Type": "application/json"
                },

                body: JSON.stringify({
                    prompt: prompt,
                    model: model || null
                })
            }
        );


        const data = await response.json();


        if (!response.ok) {

            throw new Error(
                data.detail
                    ? JSON.stringify(data.detail, null, 2)
                    : "Task execution failed."
            );
        }


        statusElement.textContent =
            data.status || "completed";


        taskIdElement.textContent =
            data.id || "-";


        resultElement.textContent =
            JSON.stringify(
                data.result,
                null,
                2
            );


    } catch (error) {

        statusElement.textContent =
            "Error";

        resultElement.textContent =
            error.message;

    } finally {

        runButton.disabled = false;
    }

});

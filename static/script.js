"use strict";

const button = document.getElementById("testButton");
const message = document.getElementById("message");

button.addEventListener("click", () => {
    message.textContent = "JavaScript is working!";
});
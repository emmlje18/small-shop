const optionRows = document.querySelector("#option-rows");
const optionRowTemplate = document.querySelector("#option-row-template");
const addOptionButton = document.querySelector("#add-option");

function updateRemoveButtons() {
  const removeButtons = optionRows.querySelectorAll(".remove-option");
  removeButtons.forEach((button) => {
    button.disabled = removeButtons.length === 1;
  });
}

function removeOption(event) {
  if (!event.target.classList.contains("remove-option")) {
    return;
  }
  event.target.closest(".option-row").remove();
  updateRemoveButtons();
}

addOptionButton.addEventListener("click", () => {
  optionRows.append(optionRowTemplate.content.cloneNode(true));
  updateRemoveButtons();
});

optionRows.addEventListener("click", removeOption);
updateRemoveButtons();

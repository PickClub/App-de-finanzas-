"use strict";

const form = document.querySelector("#deletion");
const email = document.querySelector("#email");
const password = document.querySelector("#password");
const confirmed = document.querySelector("#confirmed");
const submit = document.querySelector("#submit");
const status = document.querySelector("#status");

let pending = false;
let complete = false;
form.addEventListener("submit", async event => {
  event.preventDefault();
  if (pending || complete || !confirmed.checked) return;
  pending = true;
  submit.disabled = true;
  status.textContent = status.dataset.pending;
  try {
    const body = JSON.stringify({
      email: email.value, password: password.value, confirmed: confirmed.checked,
    });
    password.value = "";
    const response = await fetch("/api/auth/account/delete-web", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      credentials: "omit",
      cache: "no-store",
      redirect: "error",
      body,
    });
    complete = response.status === 204;
    status.textContent = complete ? status.dataset.complete : status.dataset.unconfirmed;
    if (complete) form.reset();
  } catch {
    status.textContent = status.dataset.unconfirmed;
  } finally {
    pending = false;
    submit.disabled = complete;
  }
});
submit.disabled = false;

// ruleid: parse-dont-validate.validate-returns-void-typescript
function validateEmail(s: string): void {
    if (!s.includes("@")) throw new Error("invalid");
}
// ruleid: parse-dont-validate.check-returns-boolean-typescript
function isValidEmail(s: string): boolean {
    return s.includes("@");
}
// ok: parse-dont-validate.validate-returns-void-typescript
function parseEmail(s: string): Email {
    if (!s.includes("@")) throw new Error("invalid");
    return s as Email;
}

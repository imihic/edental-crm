import { z } from "zod";

export const codeSchema = z.object({
  code: z.string().trim().regex(/^\d{6}$/, "auth.validation.codeInvalid"),
});

export const loginSchema = z.object({
  email: z
    .string()
    .trim()
    .min(1, "auth.validation.emailRequired")
    .pipe(z.email("auth.validation.emailInvalid")),
  password: z.string().min(1, "auth.validation.passwordRequired"),
});

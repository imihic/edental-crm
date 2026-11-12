import { z } from "zod";

export function isValidOib(value: string): boolean {
  if (!/^[0-9]{11}$/.test(value)) return false;
  let a = 10;
  for (const ch of value.slice(0, 10)) {
    a = (a + Number(ch)) % 10;
    if (a === 0) a = 10;
    a = (a * 2) % 11;
  }
  let check = 11 - a;
  if (check === 10) check = 0;
  return check === Number(value[10]);
}

const optionalEmail = z
  .string()
  .trim()
  .refine((v) => v === "" || z.email().safeParse(v).success, "people.validation.emailInvalid");

export const patientFormSchema = z.object({
  first_name: z.string().trim().min(1, "people.validation.firstNameRequired").max(100, "people.validation.tooLong"),
  last_name: z.string().trim().min(1, "people.validation.lastNameRequired").max(100, "people.validation.tooLong"),
  date_of_birth: z
    .string()
    .trim()
    .refine((v) => v === "" || /^\d{4}-\d{2}-\d{2}$/.test(v), "people.validation.dateInvalid"),
  phone: z.string().trim().max(40, "people.validation.tooLong"),
  email: optionalEmail,
  oib: z.string().trim().refine((v) => v === "" || isValidOib(v), "people.validation.oibInvalid"),
  address: z.string().trim().max(300, "people.validation.tooLong"),
  notes: z.string().trim().max(500, "people.validation.tooLong"),
  preferred_language: z.enum(["hr", "en"]),
  preferred_clinic_id: z.string(),
});

export type PatientFormValues = z.infer<typeof patientFormSchema>;

export const contactSchema = z.object({
  full_name: z.string().trim().min(1, "people.validation.fullNameRequired").max(200, "people.validation.tooLong"),
  phone: z.string().trim().max(40, "people.validation.tooLong"),
  email: optionalEmail,
});

const emailRun = crypto.randomUUID().slice(0, 8);

export function fakeEmail(label: string, domain: string = "example.test"): string {
  return label + "-" + emailRun + "@" + domain;
}

export function fakePassword(): string {
  return crypto.randomUUID();
}

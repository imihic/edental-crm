import { writeFile } from "node:fs/promises";
import openapiTS, { astToString } from "openapi-typescript";

const input = new URL("../../openapi.json", import.meta.url);
const output = new URL("../src/api/schema.d.ts", import.meta.url);
const schema = await openapiTS(input);
await writeFile(output, astToString(schema, { formatOptions: { removeComments: true } }));

import { fireEvent, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";
import { describe, expect, it } from "vitest";

import { Field } from "./Field";

function Harness({ start = 80 }: { start?: number }) {
  const [value, setValue] = useState(start);
  return <Field label="Altura" value={value} onChange={setValue} min={5} max={120} unit="m" />;
}

describe("Field", () => {
  it("lets a multi-digit value be typed past a first digit below the minimum", async () => {
    render(<Harness />);
    const input = screen.getByLabelText("Altura");
    await userEvent.clear(input);
    await userEvent.type(input, "30");
    expect(input).toHaveValue(30); // not 50: "3" must not be forced up to the minimum of 5
  });

  it("applies an in-range value at once and clamps a too-large one when leaving the field", async () => {
    render(<Harness />);
    const input = screen.getByLabelText("Altura");
    await userEvent.clear(input);
    await userEvent.type(input, "45");
    expect(screen.getByLabelText("Altura (controle deslizante)")).toHaveValue("45");
    await userEvent.clear(input);
    await userEvent.type(input, "999");
    await userEvent.tab();
    expect(input).toHaveValue(120);
  });

  it("puts back the last value when the field is left empty", async () => {
    render(<Harness start={60} />);
    const input = screen.getByLabelText("Altura");
    await userEvent.clear(input);
    await userEvent.tab();
    expect(input).toHaveValue(60);
  });

  it("follows the slider", () => {
    render(<Harness />);
    fireEvent.change(screen.getByLabelText("Altura (controle deslizante)"), {
      target: { value: "90" },
    });
    expect(screen.getByLabelText("Altura")).toHaveValue(90);
  });
});

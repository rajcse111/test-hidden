import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { App } from "./App";

describe("App", () => {
  it("renders the overlay shell", () => {
    render(<App />);
    expect(screen.getByText("AI Interview Assistant")).toBeInTheDocument();
  });
});


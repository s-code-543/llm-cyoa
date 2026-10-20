import { afterEach, expect, test } from "vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router";
import { AdminLayout } from "./AdminLayout";

afterEach(cleanup);

test("mobile section selector follows nested routes and navigates between sections", async () => {
  render(
    <MemoryRouter initialEntries={["/manage/providers/1/models"]}>
      <Routes>
        <Route path="/manage" element={<AdminLayout />}>
          <Route
            path="providers/:id/models"
            element={<h1>Provider catalog</h1>}
          />
          <Route path="chats" element={<h1>User chats</h1>} />
        </Route>
      </Routes>
    </MemoryRouter>,
  );
  const selector = screen.getByRole("button", { name: /Admin section/ });
  expect(selector).toHaveTextContent("Providers");
  fireEvent.click(selector);
  fireEvent.click(await screen.findByRole("option", { name: "Chats" }));
  expect(
    await screen.findByRole("heading", { name: "User chats" }),
  ).toBeTruthy();
  expect(selector).toHaveTextContent("Chats");
});

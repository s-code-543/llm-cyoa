import { useState } from "react";
import { Link } from "react-router";
import { useQuery } from "@tanstack/react-query";
import { getAdminChats } from "../../api/admin";
import { Failure, Loading } from "./ui";

export function ChatsPage() {
  const [search, setSearch] = useState("");
  const [offset, setOffset] = useState(0);
  const chats = useQuery({
    queryKey: ["admin", "chats", search, offset],
    queryFn: () => getAdminChats(search, offset),
  });
  return (
    <>
      <h1>Chats</h1>
      <p>Inspect conversations and pipeline debug details for all users.</p>
      <div className="toolbar">
        <input
          aria-label="Search chats"
          placeholder="Search by user, title, or chat ID"
          value={search}
          onChange={(e) => {
            setSearch(e.target.value);
            setOffset(0);
          }}
        />
      </div>
      {chats.isPending && <Loading />}
      <Failure error={chats.error} />
      {chats.data && (
        <>
          {chats.data.chats.length ? (
            <table className="table">
              <thead>
                <tr>
                  <th>Chat</th>
                  <th>User</th>
                  <th>Last updated</th>
                  <th />
                </tr>
              </thead>
              <tbody>
                {chats.data.chats.map((chat) => (
                  <tr key={chat.id}>
                    <td>{chat.title}</td>
                    <td>{chat.owner}</td>
                    <td>{new Date(chat.updated_at).toLocaleString()}</td>
                    <td>
                      <Link
                        to={`/chat?conversation_id=${encodeURIComponent(chat.id)}&debug=true`}
                      >
                        Inspect chat
                      </Link>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          ) : (
            <p className="empty">No chats match.</p>
          )}
          <div className="toolbar">
            <button disabled={!offset} onClick={() => setOffset(offset - 50)}>
              Previous
            </button>
            <button
              disabled={!chats.data.has_more}
              onClick={() => setOffset(offset + 50)}
            >
              Next
            </button>
          </div>
        </>
      )}
    </>
  );
}

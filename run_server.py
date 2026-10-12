"""Запуск сервера:  python run_server.py [--host 127.0.0.1] [--port 8765] [--data server_data]"""
import argparse

from tabledb.server import serve

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Сервер табличної бази даних")
    parser.add_argument("--host", default="127.0.0.1",
                        help="адреса прослуховування (0.0.0.0 — доступ із мережі; автентифікації немає!)")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--data", default="server_data", help="тека для файлів баз (.tdb)")
    args = parser.parse_args()
    serve(args.host, args.port, args.data)

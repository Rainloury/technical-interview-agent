interface CursorPage {
  next_cursor: string | null;
}

// 与后端 {items, next_cursor} 游标分页契约对应的 useInfiniteQuery 样板参数。
export const cursorPageParams = {
  initialPageParam: null as string | null,
  getNextPageParam: (lastPage: CursorPage): string | null => lastPage.next_cursor,
};
